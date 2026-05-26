import os
import sys
import asyncio
import time
import requests
import json
import math
import motor.motor_asyncio
import re
import certifi
from huggingface_hub import InferenceClient, AsyncInferenceClient
from openai import OpenAI
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel
from bs4 import BeautifulSoup
from fastapi.middleware.cors import CORSMiddleware
from duckduckgo_search import DDGS
from llm.gemma_client import GemmaEndpointClient, SYSTEM_PROMPT

sys.path.insert(0, os.path.dirname(__file__))

# -------------------- GLOBAL GENAI CLIENT --------------------
HF_TOKEN = os.getenv("HF_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GENAI_CLIENT = AsyncInferenceClient(
    token=HF_TOKEN,
    timeout=60
)
GEMMA_CLIENT = GemmaEndpointClient.from_env()
GROQ_CLIENT = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY,
) if GROQ_API_KEY else None


# -------------------- CORRECTED SEMANTIC SEARCH --------------------
class SemanticSearch:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SemanticSearch, cls).__new__(cls)
            # Initialize InferenceClient with the router base URL as required for Render
            cls._instance.model_id = "sentence-transformers/all-mpnet-base-v2"
            cls._instance.hf_token = HF_TOKEN
            cls._instance.client = InferenceClient(
                token=cls._instance.hf_token,
                headers={"X-Wait-For-Model": "true"}
            )
            cls._instance.entities = []
            cls._instance.embeddings = None
            cls._instance.embeddings_path = os.path.join(os.path.dirname(__file__), "embeddings.json")
        return cls._instance

    def _query_api(self, inputs):
        if not self.hf_token:
            return None
        try:
            # InferenceClient.feature_extraction explicitly requests the feature-extraction task
            response = self.client.feature_extraction(inputs, model=self.model_id)
            # Convert to list if it's a numpy array (InferenceClient may return numpy if installed)
            if hasattr(response, "tolist"):
                return response.tolist()
            return response
        except Exception as e:
            print(f"HF API Error via InferenceClient: {e}")
            return None

    def encode_entities(self, entities, batch_size=32):
        new_embeddings = []
        for i in range(0, len(entities), batch_size):
            batch = entities[i : i + batch_size]
            
            response = self._query_api(batch)
            if isinstance(response, list):
                for item in response:
                    # Logic to flatten: ensure we get a 1D vector per sentence
                    # API sometimes returns [[v1, v2...]] (3D) instead of [v1, v2...] (2D)
                    temp = item
                    while isinstance(temp, list) and len(temp) > 0 and isinstance(temp[0], list):
                        temp = temp[0]
                    new_embeddings.append(temp)
            else:
                print(f"Error encoding batch starting at {i}. Response: {response}")
                return
        if len(new_embeddings) == len(entities):
            self.entities = entities
            self.embeddings = new_embeddings
            with open(self.embeddings_path, "w") as f:
                json.dump({
                    "entities": self.entities,
                    "embeddings": self.embeddings,
                    "model": self.model_id
                }, f)
            print(f"Successfully cached {len(entities)} embeddings.")
    def load_embeddings(self):
        if os.path.exists(self.embeddings_path):
            try:
                with open(self.embeddings_path, "r") as f:
                    data = json.load(f)
                # Check if cached for the same model
                if data.get("model") != self.model_id:
                    return False
                self.entities = data["entities"]
                self.embeddings = data["embeddings"]
                return True
            except Exception as e:
                print(f"Error loading embeddings: {e}")
                return False
        return False
    def search(self, query, threshold=0.6):
        if self.embeddings is None or not self.entities:
            return []  

        query_embedding_list = self._query_api([query])
        if not isinstance(query_embedding_list, list) or not query_embedding_list:
            return []
        # Extract and flatten query embedding
        query_embedding = query_embedding_list[0]
        while isinstance(query_embedding, list) and len(query_embedding) > 0 and isinstance(query_embedding[0], list):
            query_embedding = query_embedding[0]
        def cosine_similarity(a, b):
            dot_product = sum(x * y for x, y in zip(a, b))
            mag_a = math.sqrt(sum(x * x for x in a))
            mag_b = math.sqrt(sum(y * y for y in b))
            return dot_product / (mag_a * mag_b) if mag_a * mag_b > 0 else 0
        results = []
        for i, emb in enumerate(self.embeddings):
            score = cosine_similarity(query_embedding, emb)
            if score >= threshold:
                results.append({"name": self.entities[i], "score": score})
        results.sort(key=lambda x: x["score"], reverse=True)
        return results
from contextlib import asynccontextmanager

semantic_search = SemanticSearch()

# Database configuration
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("MONGODB_DB_NAME", "ingres_db")
MONGODB_TIMEOUT_MS = int(os.getenv("MONGODB_TIMEOUT_MS", "5000"))
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "*").split(",")
    if origin.strip()
]

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize MongoDB client
    app.state.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(
        MONGODB_URI,
        serverSelectionTimeoutMS=MONGODB_TIMEOUT_MS,
        tlsCAFile=certifi.where(),
    )
    app.state.db = app.state.mongo_client[DB_NAME]

    # Initialize semantic search and cache locations
    try:
        db = app.state.db
        assessments_coll = db.assessments

        # Get one document to determine field names
        sample = await assessments_coll.find_one()
        if sample:
            cols = list(sample.keys())
            state_col = next((c for c in cols if "state" in c.lower()), "state")
            dist_col = next((c for c in cols if "district" in c.lower()), "district_name")
            block_col = next((c for c in cols if "block" in c.lower() or "taluka" in c.lower()), "block_name")

            app.state.states_list = await assessments_coll.distinct(state_col)
            app.state.districts_list = await assessments_coll.distinct(dist_col)
            blocks = await assessments_coll.distinct(block_col)

            app.state.states_list = [s for s in app.state.states_list if s]
            app.state.districts_list = [d for d in app.state.districts_list if d]
            blocks = [b for b in blocks if b]
        else:
            app.state.states_list = []
            app.state.districts_list = []
            blocks = []

        if not semantic_search.load_embeddings() and semantic_search.hf_token:
                # Unified corpus: locations + dictionary keys
                knowledge_keys = list(KNOWLEDGE_BASE.keys())
                tips_keys = list(TIPS.keys())
                why_keys = list(WHY_MAP.keys())
                all_entities = list(set(app.state.states_list + app.state.districts_list + blocks + knowledge_keys + tips_keys + why_keys))
                if all_entities:
                    semantic_search.encode_entities(all_entities)
    except Exception as e:
        print(f"Error initializing: {e}")
    yield
    app.state.mongo_client.close()

app = FastAPI(lifespan=lifespan)

# -------------------- ML ROUTES --------------------
try:
    from routers.ml_routes import router as ml_router
    app.include_router(ml_router)
    print("ML routes loaded successfully.")
except Exception as e:
    print(f"Warning: Could not load ML routes: {e}")

# -------------------- SMART GENAI LAYER --------------------
async def get_smart_response(user_query: str, context: str):
    """
    Generates a natural language explanation using Llama 3 via HF Inference API.
    Only uses verified context provided by the rule-based/DB logic.
    """
    client = GENAI_CLIENT
    context = context[:3500]

    system_prompt = (
        f"{SYSTEM_PROMPT}\n"
        "GUIDELINES:\n"
        "If extraction > 100%, use a concerned but professional tone.\n"
        "Use Indian terminology (e.g., 'Taluka', 'Lakh', 'Kharif/Rabi') where appropriate.\n"
        "If contaminants like Arsenic or Fluoride are mentioned, prioritize health warnings.\n"
        "Keep responses under 200 words unless the user asks for a deep dive."
        "Never invent statistics or causes.\n"
        "Do not hallucinate or assume missing data."
    )

    messages = [
        {"role": "system", "content": system_prompt},
    
    # 1. THE NORTHERN/AGRICULTURAL PROTOTYPE (Punjab, Haryana, West UP)
        {"role": "user", "content": "USER QUESTION: Why is Haryana water low?\nVERIFIED CONTEXT: Extraction 135%, Over-exploited. Major crops: Wheat and Paddy."},
        {"role": "assistant", "content": "Haryana's groundwater is critically over-exploited (135%). In the breadbasket regions of North India, intensive irrigation for cereal crops pulls water faster than the monsoon recharges it. **Tip:** Shift to 'Direct Seeded Rice' (DSR) and increase crop diversification."},

    # 2. THE PENINSULAR/HARD-ROCK PROTOTYPE (Karnataka, Maharashtra, Telangana)
        {"role": "user", "content": "USER QUESTION: What's the status in Bengaluru?\nVERIFIED CONTEXT: Extraction 98%, Stressed. Hard rock terrain, rapid urban growth."},
        {"role": "assistant", "content": "Bengaluru is facing 'Stressed' conditions (98%). Unlike the North, South India's hard-rock terrain has limited 'sponginess' to hold water. Rapid urbanization covers recharge areas with concrete. **Tip:** Mandatory rooftop rainwater harvesting is the only way to revive these borewells."},

    # 3. THE COASTAL/SALINITY PROTOTYPE (Gujarat, Tamil Nadu, Odisha)
        {"role": "user", "content": "USER QUESTION: Is the water okay in coastal Gujarat?\nVERIFIED CONTEXT: Extraction 80%, Salinity ingress reported."},
        {"role": "assistant", "content": "In coastal Gujarat, the 80% extraction rate is leading to 'Salinity Ingress.' As fresh groundwater levels drop, the sea seeps into the aquifers, making water salty. **Tip:** Stop over-pumping near the coast and build 'Tidal Regulators' to keep seawater out."},

    # 4. THE MOUNTAIN/SPRING PROTOTYPE (Himachal, Uttarakhand, North East)
        {"role": "user", "content": "USER QUESTION: Water status in Meghalaya?\nVERIFIED CONTEXT: Extraction 15%, Safe. High rainfall, spring-based systems."},
        {"role": "assistant", "content": "Meghalaya is in the 'Safe' zone (15%). In the North East, water management is about 'Springsheds.' Even with high rain, water can run off quickly. **Tip:** Protect forest cover around community springs (Chasmas) to ensure year-round flow."},

    # THE REAL USER QUERY (This stays at the end)
        {"role": "user", "content": f"USER QUESTION:\n{user_query}\n\nVERIFIED CONTEXT:\n{context}"}
    ]

    if GROQ_CLIENT:
        try:
            def complete_with_groq():
                response = GROQ_CLIENT.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=messages,
                    temperature=0.2,
                    max_tokens=300,
                )
                return response.choices[0].message.content or ""

            text = await run_in_threadpool(complete_with_groq)
            for ch in text:
                yield ch
                await asyncio.sleep(0.01)
            return
        except Exception as e:
            print(f"Groq error: {e}")

    if GEMMA_CLIENT.is_configured:
        try:
            text = await run_in_threadpool(GEMMA_CLIENT.complete, messages, 300)
            for ch in text:
                yield ch
                await asyncio.sleep(0.01)
            return
        except Exception as e:
            print(f"Gemma endpoint error: {e}")

    if not HF_TOKEN:
        return

    try:
        # chat_completion yields chunks incrementally if stream=True
        # This aligns with the 'conversational' task required by some providers
        stream = await client.chat_completion(
            model="meta-llama/Meta-Llama-3-8B-Instruct",
            messages=messages,
            stream=True,
            max_tokens=300
        )
        async for chunk in stream:
            # ---- SAFETY GUARDS (CRITICAL) ----
            if not hasattr(chunk, "choices") or not chunk.choices:
                continue

            choice = chunk.choices[0]
            if not hasattr(choice, "delta") or not choice.delta:
                continue

            token = getattr(choice.delta, "content", None)
            if not token:
                continue

            safe = token.replace("\n", " ")
            for ch in safe:
                yield ch
                await asyncio.sleep(0.015)
    except Exception as e:
        print(f"GenAI Error: {e}")
        # When an error occurs, the generator simply stops.
        # The caller should handle the fallback if no text was generated.

# -------------------- SERVICES --------------------
def get_wikipedia_image(query):
    """Fallback to fetch image from Wikipedia if search fails."""
    try:
        # Simple heuristic: capitalize first letter for Wikipedia
        term = query.title().replace(' ', '_')
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{term}"
        headers = {"User-Agent": "MyWaterBot_AI_Bot/1.0 (support@mywaterbot.ai)"}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if "thumbnail" in data:
                return data["thumbnail"]["source"]
    except Exception:
        pass
    return None

def get_image_url(query):
    """Fetches a relevant image URL using DuckDuckGo search with Wikipedia fallback."""
    try:
        with DDGS() as ddgs:
            # We add 'groundwater' or similar context to refine results if needed,
            # but for specific terms like 'aquifer', 'borewell', it should be fine.
            results = ddgs.images(query, max_results=1)
            if results:
                return results[0]['image']
    except Exception as e:
        print(f"Image search error for '{query}': {e}")

    return get_wikipedia_image(query)

def get_latest_news():
    query = "groundwater levels India"
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}&tbm=nws"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        # Check for 403 or other non-200 responses
        if response.status_code != 200:
            return get_cached_news()

        soup = BeautifulSoup(response.text, 'html.parser')
        headlines = []

        # Google News headlines in search results are typically in <h3> tags
        for item in soup.find_all('h3'):
            text = item.get_text().strip()
            if text:
                headlines.append(text)
            if len(headlines) == 3:
                break

        if not headlines:
            return get_cached_news()

        return headlines

    except Exception:
        # Fallback mechanism for request failures or parsing errors
        return get_cached_news()

def get_cached_news():
    return [
        "Groundwater levels in India showing signs of improvement in some regions due to better monsoon.",
        "New CGWB report highlights critical depletion in northwestern states.",
        "Government announces new initiatives for community-led groundwater management."
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials="*" not in CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

class WaterQuery(BaseModel):
    message: str
    stream: bool = False

last_data_cache = {"data": []}

# -------------------- KNOWLEDGE --------------------
KNOWLEDGE_BASE = {
    "groundwater": "Groundwater is water that has found its way down from the Earth’s surface into the cracks and spaces in soil, sand and rock.The largest use for groundwater is to irrigate crops.",
    "extraction": "Ground water overuse or overexploitation is defined as a situation in which, over a period of time, theaverage extraction rate from aquifers is greater than the average recharge rate. This leads to a decline in the groundwater levels and may also result in other adverse consequences such as land subsidence, reduced water quality, and ecological damage.",
    "recharge": "Recharge is the process by which rainfall replenishes underground aquifers.",
    "over-exploited": "An over-exploited region extracts more groundwater than it naturally recharges.",
    "safe": "A 'Safe' category means groundwater extraction is below 70% of available recharge.",
    "critical": "A 'Critical' category indicates extraction is between 90% and 100% of recharge capacity.",
    "stage": "Stage of Extraction is the ratio of groundwater used to groundwater available.",
    "aquifer": "An aquifer is an underground layer of water-bearing permeable rock, Aquifers are typically made up of gravel, sand, sandstone, or fractured rock, like limestone. Water can move through these materials because they have large connected spaces that make them permeable. The speed at which groundwater flows depends on the size of the spaces in the soil or rock and how well the spaces are connected.",
    "borewell": "A borewell is a deep, narrow hole drilled into the ground to access groundwater from aquifers.",
    "watershed": "A watershed is an area of land where all the water that falls in it and drains off it goes to a common outlet, such as a river or lake.",
    "salinity": "Salinity refers to the concentration of dissolved salts in water. High salinity can make groundwater unsuitable for drinking or irrigation.",
    "master plan": "The Master Plan for Artificial Recharge to Groundwater-2020 envisages construction of about 1.42 crore rain water harvesting and artificial recharge structures.",
    "gujarat salinity": "Coastal Gujarat faces seawater intrusion due to over-pumping, leading to increased salinity in groundwater.",
    "paddy water": "Rice (paddy) is a water-intensive crop, often requiring 3,000 to 5,000 liters of water to produce 1 kg of grain.",
    "sugarcane": "Sugarcane is another high water-consuming crop, contributing significantly to groundwater depletion in Maharashtra and UP.",
    "millets": "Millets are climate-smart crops that require significantly less water than rice or wheat, making them ideal for water-stressed regions.",
    "atal bhujal yojana": "Atal Bhujal Yojana (ATAL JAL) is a Central Sector Scheme for sustainable groundwater management with community participation.",
    "cgwb": "The Central Ground Water Board (CGWB) is the apex organization in India for providing scientific inputs for management, exploration, and monitoring of groundwater.",
    "pmksy": "Pradhan Mantri Krishi Sinchayee Yojana (PMKSY) focuses on 'Har Khet Ko Pani' and 'Per Drop More Crop'.",
    "drip irrigation": "Drip irrigation delivers water directly to the plant's root zone, reducing evaporation and runoff, saving up to 40-70% water.",
    "arsenic": "Arsenic contamination is a major health concern in the Ganga-Brahmaputra fluvial plains, including West Bengal, Bihar, and UP.",
    "fluoride": "Excessive fluoride in groundwater can lead to dental and skeletal fluorosis; it is common in states like Rajasthan and Telangana.",
    "nitrate": "Nitrate pollution in groundwater often results from excessive use of fertilizers in agriculture and improper sewage disposal.",
    "jal shakti abhiyan": "Jal Shakti Abhiyan is a campaign for water conservation and water security in India.",
    "national aquifer mapping": "The NAQUIM program aims to delineate aquifers, their characterization and develop plans for sustainable management.",
    "virtual water": "Virtual water is the hidden flow of water if food or other commodities are traded from one place to another.",
    "over-pumping": "Over-pumping occurs when groundwater is withdrawn faster than the rate of recharge, causing water tables to drop.",
    "seawater intrusion": "In coastal areas, over-extraction of groundwater can cause seawater to flow into freshwater aquifers.",
    "check dam": "A check dam is a small, sometimes temporary, dam constructed across a swale, drainage ditch, or waterway to counteract erosion by reducing water velocity.",
    "percolation tank": "Percolation tanks are artificially created surface water bodies, submerging a highly permeable land area so that surface runoff is made to percolate and recharge the ground water storage.",
    "dug well": "Dug wells are shallow wells excavated into the ground, usually with a diameter of several meters.",
    "greywater": "Greywater is gently used water from bathroom sinks, showers, tubs, and washing machines. It is not water that has come into contact with feces.",
    "blackwater": "Blackwater is wastewater from toilets, which likely contains pathogens.",
    "infiltration": "Infiltration is the process by which water on the ground surface enters the soil.",
    "transpiration": "Transpiration is the process by which moisture is carried through plants from roots to small pores on the underside of leaves, where it changes to vapor and is released to the atmosphere.",
    "evapotranspiration": "Evapotranspiration is the sum of evaporation and plant transpiration from the Earth's land and ocean surface to the atmosphere.",
    "water table": "The water table is the upper surface of the zone of saturation. The zone of saturation is where the pores and fractures of the ground are saturated with water.",
    "confined aquifer": "A confined aquifer is an aquifer below the land surface that is saturated with water. Layers of impermeable material are both above and below the aquifer, causing it to be under pressure.",
    "unconfined aquifer": "An unconfined aquifer is an aquifer whose upper water surface (water table) is at atmospheric pressure, and thus is able to rise and fall.",
    "hydrogeology": "Hydrogeology is the area of geology that deals with the distribution and movement of groundwater in the soil and rocks of the Earth’s crust.",
    "specific yield": "Specific yield is the ratio of the volume of water that, after being saturated, can be drained by gravity to its own volume.",
    "permeability": "Permeability is a measure of the ability of a material (such as rocks) to transmit fluids.",
    "porosity": "Porosity is a measure of the void spaces in a material, and is a fraction of the volume of voids over the total volume.",
    "drawdown": "Drawdown is the reduction in the hydraulic head observed at a well in an aquifer, typically due to pumping a well as part of an aquifer test or well test.",
    "cone of depression": "A cone of depression occurs in an aquifer when groundwater is pumped from a well. In an unconfined aquifer, this is an actual depression of the water levels.",
    "baseflow": "Baseflow is the portion of streamflow that comes from 'the sum of deep subsurface flow and delayed shallow subsurface flow'.",
    "catchment area": "The catchment area is the area from which rainfall flows into a particular river or lake.",
    "siltation": "Siltation is a process by which water becomes dirty as a result of fine mineral particles in the water.",
    "desalination": "Desalination is a process that takes away mineral components from saline water.",
    "fecal coliform": "Fecal coliforms are a group of bacteria that are passed through the fecal excrement of humans, livestock and wildlife.",
    "hard water": "Hard water is water that has high mineral content. Hard water is formed when water percolates through deposits of limestone, chalk or gypsum.",
    "soft water": "Soft water is surface water that contains low concentrations of ions and in particular is low in ions of calcium and magnesium.",
    "turbidity": "Turbidity is the cloudiness or haziness of a fluid caused by large numbers of individual particles that are generally invisible to the naked eye.",
    "ph value": "The pH of water is a measure of how acidic/basic water is.",
    "tds": "Total Dissolved Solids (TDS) is a measure of the dissolved combined content of all inorganic and organic substances present in a liquid.",
    "dissolved oxygen": "Dissolved oxygen (DO) is the amount of gaseous oxygen (O2) dissolved in the water.",
    "agriculture": "Agriculture is the practice of cultivating plants and raising livestock for food, fiber, and other products. In India, agriculture is the single largest consumer of groundwater, accounting for nearly 90% of all groundwater extraction — primarily for irrigation of crops like rice, wheat, and sugarcane.",
    "groundwater depletion": "Groundwater depletion occurs when water is withdrawn from underground aquifers faster than it is naturally replenished. Major causes include over-irrigation, urbanization that reduces recharge areas, and industrial extraction. Prolonged depletion can lead to land subsidence, drying of wells, and permanent loss of aquifer storage capacity.",
    "rainfall recharge": "Rainfall recharge is the natural process by which rainwater percolates through the soil and rock layers to replenish underground aquifers. The amount of recharge depends on factors like rainfall intensity, soil type, land use, and vegetation cover. In India, most groundwater recharge happens during the monsoon season (June–September).",
    "water conservation": "Water conservation refers to the strategies and practices aimed at reducing water usage, preventing wastage, and protecting water resources for future generations. It is essential because freshwater is a finite resource — only about 1% of Earth's water is accessible for human use. Key methods include rainwater harvesting, efficient irrigation, wastewater recycling, and reducing household leaks.",
    "water scarcity": "Water scarcity occurs when the demand for water exceeds the available supply in a region. Causes include over-extraction of groundwater, climate change reducing rainfall patterns, population growth, pollution of freshwater sources, and inefficient agricultural practices. India faces significant water scarcity, with NITI Aayog reporting that 21 major cities could run out of groundwater in the near future.",
    "sustainable groundwater management": "Sustainable groundwater management involves using groundwater resources at a rate that does not exceed the natural recharge rate, ensuring long-term availability. Key practices include: community-based water monitoring, crop diversification to reduce irrigation demand, artificial recharge structures (check dams, percolation tanks), regulatory frameworks for borewell drilling, and adoption of water-efficient technologies like drip irrigation.",
    "water cycle": "The water cycle (hydrological cycle) is the continuous movement of water within the Earth and atmosphere. It includes evaporation from water bodies, transpiration from plants, condensation into clouds, precipitation as rain or snow, surface runoff, and infiltration into groundwater. Understanding the water cycle is fundamental to managing water resources sustainably.",
}

# -------------------- CONTAMINANTS --------------------
CONTAMINANT_DATA = {
    "rajasthan": ["Fluoride", "Nitrate"],
    "punjab": ["Nitrate", "Arsenic"],
    "haryana": ["Fluoride", "Nitrate"],
    "west bengal": ["Arsenic", "Fluoride"],
    "bihar": ["Arsenic", "Iron"],
    "uttar pradesh": ["Fluoride", "Arsenic"],
    "karnataka": ["Fluoride", "Nitrate"],
    "tamil nadu": ["Fluoride", "Salinity"],
    "gujarat": ["Salinity", "Fluoride"],
    "andhra pradesh": ["Fluoride"],
    "delhi": ["Nitrate", "Fluoride"],
    "kolar": ["Fluoride"],
    "bangalore": ["Nitrate"],
    "tumkur": ["Fluoride"],
    "chikkaballapura": ["Fluoride"],
    "raichur": ["Arsenic"],
    "gulbarga": ["Fluoride"]
}

# -------------------- WHY MAP --------------------
WHY_MAP = {
    "punjab": "High dependence on groundwater for water-intensive crops like paddy and wheat; subsidized electricity leads to over-pumping.",
    "haryana": "Intensive agricultural practices and high irrigation demand for cereal crops beyond natural recharge levels.",
    "delhi": "Massive population density, rapid urbanization, and high concretization preventing rainwater from recharging aquifers.",
    "uttar pradesh": "Heavy agricultural extraction in western districts for sugarcane; industrial pollution in areas like Kanpur (tanneries).",
    "rajasthan": "Arid climate, extremely low rainfall, and high evaporation rates; historic reliance on deep fossil water.",
    "gujarat": "Industrial demand and high salinity ingress in coastal areas; intensive irrigation in districts like Mehsana.",
    "maharashtra": "Hard rock (Basalt) terrain with low storage capacity; over-extraction for sugarcane in the Marathwada/Vidarbha belts.",
    "karnataka": "Hard rock terrain (Deccan Trap) with low storage; high borewell density for IT hubs and agriculture.",
    "tamil nadu": "Over-reliance on groundwater due to surface water scarcity and frequent failures of the monsoon.",
    "bengaluru": "Rapid expansion into peripheral zones without piped water; over-reliance on private tankers and deep borewells.",
    "chennai": "Coastal location leading to seawater intrusion; high domestic demand following reservoir failures.",
    "gurugram": "Extremely high construction demand and deep extraction for high-rise residential complexes.",
    "jaipur": "Semi-arid climate coupled with tourism and luxury residential demand exceeding replenishment.",
    "odisha": "Coastal districts face salinity ingress due to proximity to the sea, while inland areas have limited storage in hard rock aquifers.",
    "bihar": "High levels of arsenic and fluoride contamination in certain belts; seasonal flooding can also impact groundwater quality.",
    "assam": "Despite abundant rainfall, certain regions face high iron and arsenic content in shallow aquifers.",
    "kerala": "Laterite soil has high permeability but low storage, leading to seasonal water scarcity despite high annual rainfall."
}

# -------------------- CONSERVATION TIPS --------------------
TIPS = {
    "conservation": "To conserve groundwater: 1. Install rainwater harvesting systems. 2. Use drip or sprinkler irrigation. 3. Recycle greywater for gardening. 4. Fix leaks promptly.",
    "harvesting": "Rainwater harvesting involves collecting and storing rainwater from rooftops or ground surfaces to recharge aquifers or for direct use.",
    "farming": "Sustainable farming tips: 1. Adopt crop rotation. 2. Grow less water-intensive crops like millets. 3. Use mulch to retain soil moisture.",
    "pollution": "Prevent pollution by: 1. Reducing fertilizer and pesticide use. 2. Proper disposal of hazardous waste. 3. Ensuring septic systems are well-maintained.",
    "crop choice": "Switch from water-intensive crops like paddy to millets or pulses in water-stressed regions.",
    "mulching": "Use organic mulch in fields to reduce evaporation from the soil surface.",
    "smart irrigation": "Adopt sensors and automated systems to provide water to crops only when needed.",
    "community participation": "Form Water User Associations to collectively manage and monitor groundwater usage in villages.",
    "well recharging": "Redirect surplus monsoon runoff into defunct dug wells to recharge local aquifers.",
}

# -------------------- LAYERED RESPONSES --------------------
LAYERED_METADATA = {
    "groundwater": {
        "why": "It's the primary source of water for half of the world's population and essential for agriculture.",
        "impact": "Depletion threatens food security and domestic water supply.",
        "tip": "Reduce wastage in households and adopt rainwater harvesting."
    },
    "aquifer": {
        "why": "Acts as a natural underground reservoir for storing water.",
        "impact": "Over-extraction can cause land subsidence and permanent loss of storage capacity.",
        "tip": "Protect recharge areas from urban sprawl and pollution."
    },
    "recharge": {
        "why": "It's the natural process that keeps our groundwater levels stable.",
        "impact": "Low recharge leads to dropping water tables and drying wells.",
        "tip": "Use check dams and percolation tanks to enhance natural recharge."
    },
    "extraction": {
        "why": "High extraction rates indicate we are using water faster than nature can replenish it.",
        "impact": "Leads to water stress, saline ingress in coastal areas, and higher pumping costs.",
        "tip": "Switch to water-efficient irrigation methods like drip or sprinklers."
    }
}

def format_layered_response(term, definition):
    meta = LAYERED_METADATA.get(term.lower(), {
        "why": "Crucial for understanding water sustainability and resource management.",
        "impact": "Directly affects long-term water availability and quality for future generations.",
        "tip": "Support local water conservation initiatives and stay informed about water levels."
    })
    return (
        f"**Definition:** {definition}\n\n"
        f"**Why it matters:** {meta['why']}\n\n"
        f"**Impact/Interpretation:** {meta['impact']}\n\n"
        f"**Actionable Tip:** {meta['tip']}"
    )

# -------------------- EXPLANATION ENGINE --------------------
def explain_extraction(name, value):
    if value <= 70:
        status = "relatively safe"
        meaning = "groundwater use is within sustainable limits"
        impact = "Minimal impact on water table; sustainable for future use."
        tip = "Maintain current practices and consider rainwater harvesting to stay safe."
    elif value <= 100:
        status = "stressed"
        meaning = "water usage is close to or exceeding recharge capacity"
        impact = "Lowering water tables; increased pumping costs; potential for seasonal scarcity."
        tip = "Reduce water-intensive crops; adopt drip irrigation; implement community-led recharge."
    else:
        status = "over-exploited"
        meaning = "groundwater is being extracted much faster than it can recharge"
        impact = "Rapidly falling water levels; drying borewells; long-term ecological damage; potential land subsidence."
        tip = "Urgent: Stop new borewells; shift to millets; mandatory rainwater harvesting; artificial recharge."

    return (
        f"**Definition:** Average groundwater extraction of {value}% for {name.title()}.\n\n"
        f"**Why it matters:** It indicates the balance between usage and natural replenishment.\n\n"
        f"**Impact/Interpretation:** This places it in a **{status}** category. {meaning}. {impact}\n\n"
        f"**Actionable Tip:** {tip}"
    )

def generate_data_explanation(data):
    if not data:
        return "I don't have enough data to provide an explanation."

    if len(data) == 1:
        return explain_extraction(data[0]['name'], data[0]['extraction'])

    # Comparison logic for multiple items
    sorted_data = sorted(data, key=lambda x: x['extraction'], reverse=True)
    highest = sorted_data[0]
    lowest = sorted_data[-1]

    explanation = f"### Data Comparison & Explanation\n\n"
    explanation += f"This chart compares the groundwater extraction levels of {len(data)} regions. "
    explanation += f"**{highest['name'].title()}** shows the highest extraction rate at **{highest['extraction']}%**, "

    if highest['extraction'] > 100:
        explanation += "which is categorized as **over-exploited**. "
    elif highest['extraction'] > 70:
        explanation += "which is **stressed**. "
    else:
        explanation += "which is still within **relatively safe** limits. "

    explanation += f"Meanwhile, **{lowest['name'].title()}** has the lowest rate among those shown at **{lowest['extraction']}%**. "

    gap = highest['extraction'] - lowest['extraction']
    if gap > 30:
        explanation += f"The gap of {round(gap, 2)}% highlights a significant regional disparity in water usage and recharge balance. "

    explanation += "\n\n**Actionable Insight:** Regions with extraction above 70% should prioritize water conservation and crop diversification to ensure long-term sustainability."

    return explanation

# -------------------- SUGGESTION ENGINE --------------------
def get_suggestions(user_input, found_data=None):
    suggestions = ["Conservation tips", "What is an aquifer?", "Show India map"]

    if found_data:
        # Contextual next-steps for locations
        loc_name = found_data[0]['name'].title()
        suggestions = [
            f"Why is {loc_name} stressed?",
            f"Show trend for {loc_name}",
            f"How to reduce extraction in {loc_name}"
        ]
        if len(found_data) > 1:
            suggestions.append("Show chart")
    elif "why" in user_input:
        suggestions.insert(0, "Compare Punjab and Bihar")
    elif any(k in user_input for k in ["tip", "conservation", "harvesting", "farming"]):
        suggestions.insert(0, "Search a state like Punjab")
    elif "aquifer" in user_input:
        suggestions.insert(0, "What is a water table?")
    elif "groundwater" in user_input:
        suggestions.insert(0, "How is groundwater recharged?")

    seen = set()
    unique = []
    for s in suggestions:
        if s.lower() not in seen:
            unique.append(s)
            seen.add(s.lower())
    return unique[:3]

# -------------------- FUZZY MATCHING --------------------
def _char_ratio(a: str, b: str) -> float:
    """Lightweight character-level similarity (0-1). No external deps."""
    if not a or not b:
        return 0.0
    a, b = a.lower(), b.lower()
    if a == b:
        return 1.0
    # Bigram overlap (Dice coefficient)
    def bigrams(s):
        return set(s[i:i+2] for i in range(len(s)-1)) if len(s) > 1 else {s}
    ba, bb = bigrams(a), bigrams(b)
    overlap = ba & bb
    return (2.0 * len(overlap)) / (len(ba) + len(bb)) if (ba or bb) else 0.0

def fuzzy_match_key(query: str, dictionary: dict, threshold: float = 0.55) -> str | None:
    """Find the best fuzzy-matching key in a dictionary for a query string."""
    query_lower = query.lower().strip()
    best_key = None
    best_score = 0.0
    for key in dictionary:
        # Check if key appears as substring
        if key in query_lower or query_lower in key:
            return key
        # Check individual words
        for word in query_lower.split():
            score = _char_ratio(word, key)
            if score > best_score:
                best_score = score
                best_key = key
        # Also check full query vs key
        full_score = _char_ratio(query_lower, key)
        if full_score > best_score:
            best_score = full_score
            best_key = key
    return best_key if best_score >= threshold else None

# -------------------- GREETING DETECTION --------------------
GREETING_PATTERNS = [
    "hi", "hello", "hey", "hii", "hiii", "helloo", "helo",
    "good morning", "good afternoon", "good evening", "good night",
    "howdy", "greetings", "namaste", "namaskar",
    "what's up", "whats up", "wassup", "sup",
]
GREETING_RESPONSES = [
    "Hello! I'm **INGRES**, your AI-powered groundwater intelligence assistant.\n\nI can help you with:\n- **Groundwater data** for any Indian state or district\n- **Educational questions** like 'What is an aquifer?'\n- **Comparisons** between regions\n- **Conservation tips** and solutions\n\nWhat would you like to explore today?",
    "Hey there! Welcome to **INGRES** - India's groundwater intelligence system.\n\nFeel free to ask me anything about:\n- Water levels in any state or district\n- Definitions of water-related terms\n- Why certain regions are stressed\n- Tips for water conservation\n\nHow can I help you?",
    "Namaste! I'm **INGRES**, here to help you understand India's groundwater.\n\nTry asking me:\n- 'What is groundwater depletion?'\n- 'Compare Punjab and Bihar'\n- 'Why is Rajasthan stressed?'\n- 'Conservation tips'\n\nWhat would you like to know?",
]

def detect_greeting(user_input: str) -> bool:
    """Check if the user input is a greeting."""
    cleaned = user_input.strip().lower().rstrip("!?.")
    # Exact match
    if cleaned in GREETING_PATTERNS:
        return True
    # Starts with greeting word
    for g in GREETING_PATTERNS:
        if cleaned.startswith(g + " ") or cleaned == g:
            return True
    return False

# -------------------- DEFINITION INTENT --------------------
DEFINITION_PREFIXES = [
    # Longest prefixes first to avoid partial matches
    "what do you mean by",
    "what causes", "what cause",
    "tell me about",
    "definition of", "meaning of",
    "what is", "what are", "what's", "whats",
    "define", "explain", "describe",
    "how does", "how do", "how is",
    "why is", "why are", "why does",
]

def extract_definition_subject(user_input: str) -> str | None:
    """Extract the subject from a definition query like 'what is groundwater?'"""
    cleaned = user_input.strip().lower().rstrip("?!.")
    for prefix in DEFINITION_PREFIXES:
        if cleaned.startswith(prefix + " ") or cleaned == prefix:
            subject = cleaned[len(prefix):].strip()
            # Remove articles
            for article in ["a ", "an ", "the "]:
                if subject.startswith(article):
                    subject = subject[len(article):]
            if subject:
                print(f"[INTENT] Definition detected -- prefix='{prefix}', subject='{subject}'")
            return subject if subject else None
    return None

# -------------------- THANK-YOU / BYE DETECTION --------------------
THANK_PATTERNS = ["thank", "thanks", "thankyou", "thank you", "thx", "thnks", "ty"]
BYE_PATTERNS = ["bye", "goodbye", "see you", "exit", "quit", "close"]

def detect_thanks(user_input: str) -> bool:
    cleaned = user_input.strip().lower().rstrip("!?.")
    # Use word-boundary matching to avoid false positives (e.g. 'scarcity' matching 'ty')
    for t in THANK_PATTERNS:
        if re.search(rf'\b{re.escape(t)}\b', cleaned):
            return True
    return False

def detect_bye(user_input: str) -> bool:
    cleaned = user_input.strip().lower().rstrip("!?.")
    # Use word-boundary matching to avoid false positives (e.g. 'exit strategies')
    for b in BYE_PATTERNS:
        if re.search(rf'\b{re.escape(b)}\b', cleaned):
            return True
    return False

# -------------------- VISUAL UTILS --------------------
ACTION_KEYWORDS = ["reduce", "how to", "solution", "steps", "ways", "minimize", "conserve", "prevent", "action", "improvement", "management", "reduction", "curb", "save"]
CAUSE_KEYWORDS = ["why", "cause", "reason", "factor", "trigger", "drivers", "stressed"]
TREND_KEYWORDS = ["trend", "over time", "changed", "worse", "better", "history", "years", "past"]

def detect_action_intent(user_input):
    # Check for multi-word phrases first
    if "how to" in user_input.lower():
        return True

    # Check for other keywords as whole words
    for k in ACTION_KEYWORDS:
        if k == "how to": continue
        if re.search(rf"\b{k}\b", user_input, re.IGNORECASE):
            return True
    return False

def detect_cause_intent(user_input):
    # Detects queries seeking explanations for water stress or depletion
    for k in CAUSE_KEYWORDS:
        if re.search(rf"\b{k}\b", user_input, re.IGNORECASE):
            return True
    return False

def detect_trend_intent(user_input):
    for k in TREND_KEYWORDS:
        if re.search(rf"\b{k}\b", user_input, re.IGNORECASE):
            return True
    return False

def detect_map_request(user_input):
    map_keywords = ["map", "show map", "india map", "visualize on map"]
    return any(k in user_input for k in map_keywords)

def get_visual_data(visual_type, data, context=None):
    if visual_type == "status_card":
        # data is a single location dict: {"name": "...", "extraction": ...}
        name = data["name"]
        val = data["extraction"]
        category = "Safe"
        if val > 100: category = "Over-exploited"
        elif val > 70: category = "Stressed"

        name_lower = name.lower()
        return {
            "name": name.title(),
            "extraction": val,
            "category": category,
            "trend": "Stable",
            "mainCause": WHY_MAP.get(name_lower, "Intensive agricultural and domestic usage."),
            "topRisk": f"{CONTAMINANT_DATA[name_lower][0]} contamination" if name_lower in CONTAMINANT_DATA else "Water table decline",
            "recommendedAction": "Implement rainwater harvesting and switch to drip irrigation." if val > 70 else "Maintain sustainable usage and monitor levels."
        }

    elif visual_type == "comparison_bars":
        # data is a list of location dicts
        res = []
        for d in data:
            val = d["extraction"]
            cat = "Safe"
            if val > 100: cat = "Over-exploited"
            elif val > 70: cat = "Stressed"
            res.append({
                "name": d["name"].title(),
                "extraction": val,
                "category": cat
            })
        # Sort by extraction descending
        return sorted(res, key=lambda x: x["extraction"], reverse=True)

    elif visual_type == "risk_alert":
        # data is a list of contaminants
        return {
            "contaminantList": data,
            "healthRisk": f"Long-term exposure to {', '.join(data)} can cause serious health issues like fluorosis or arsenicosis.",
            "safeForDrinking": False,
            "suggestedMitigation": "Use RO filtration, activated alumina for fluoride removal, or seek alternative safe water sources."
        }

    return None

# -------------------- MAIN API --------------------
async def get_rule_based_response(user_input: str, request: Request):
    import random
    is_map_requested = detect_map_request(user_input)

    # Normalize terms
    if "overexploited" in user_input or "over exploited" in user_input:
        user_input = user_input.replace("overexploited", "over-exploited").replace("over exploited", "over-exploited")

    SYNONYMS = {"usage": "extraction", "withdrawal": "extraction", "consumption": "extraction"}
    is_usage_query = any(w in user_input for w in ["usage", "extraction"])
    for k, v in SYNONYMS.items():
        user_input = user_input.replace(k, v)

    # --- 0. GREETING DETECTION (highest priority) ---
    if detect_greeting(user_input):
        return {
            "text": random.choice(GREETING_RESPONSES),
            "chartData": [],
            "suggestions": ["What is groundwater?", "Compare Punjab and Bihar", "Conservation tips"],
            "skip_llm": True
        }

    # --- 0b. THANK-YOU / BYE DETECTION ---
    if detect_thanks(user_input):
        return {
            "text": "You're welcome! Feel free to ask me anything else about groundwater, water conservation, or India's water resources. I'm always here to help!",
            "chartData": [],
            "suggestions": ["What is an aquifer?", "Show India map", "Conservation tips"],
            "skip_llm": True
        }
    if detect_bye(user_input):
        return {
            "text": "Goodbye! Remember - every drop counts! Feel free to come back anytime you have questions about groundwater.",
            "chartData": [],
            "suggestions": [],
            "skip_llm": True
        }

    # --- 0c. DIRECT DEFINITION INTENT (HIGHEST PRIORITY for educational queries) ---
    definition_subject = extract_definition_subject(user_input)
    if definition_subject:
        # First try exact match in KNOWLEDGE_BASE
        if definition_subject in KNOWLEDGE_BASE:
            print(f"[KB-HIT] Exact match: '{definition_subject}' found in KNOWLEDGE_BASE")
            layered_text = format_layered_response(definition_subject, KNOWLEDGE_BASE[definition_subject])
            return {
                "text": f"### {definition_subject.title()}\n\n{layered_text}",
                "chartData": [],
                "suggestions": get_suggestions(user_input),
                "skip_llm": True
            }
        # Then try fuzzy match
        fuzzy_key = fuzzy_match_key(definition_subject, KNOWLEDGE_BASE, threshold=0.50)
        if fuzzy_key:
            print(f"[KB-HIT] Fuzzy match: '{definition_subject}' -> '{fuzzy_key}' in KNOWLEDGE_BASE")
            layered_text = format_layered_response(fuzzy_key, KNOWLEDGE_BASE[fuzzy_key])
            return {
                "text": f"### {fuzzy_key.title()}\n\n{layered_text}",
                "chartData": [],
                "suggestions": get_suggestions(user_input),
                "skip_llm": True
            }
        # Check TIPS too for definition-style queries
        if definition_subject in TIPS:
            print(f"[KB-HIT] Exact match: '{definition_subject}' found in TIPS")
            return {
                "text": f"### {definition_subject.title()}\n\n{TIPS[definition_subject]}",
                "chartData": [],
                "suggestions": get_suggestions(user_input),
                "skip_llm": True
            }
        fuzzy_tip = fuzzy_match_key(definition_subject, TIPS, threshold=0.50)
        if fuzzy_tip:
            print(f"[KB-HIT] Fuzzy match: '{definition_subject}' -> '{fuzzy_tip}' in TIPS")
            return {
                "text": f"### {fuzzy_tip.title()}\n\n{TIPS[fuzzy_tip]}",
                "chartData": [],
                "suggestions": get_suggestions(user_input),
                "skip_llm": True
            }
        print(f"[KB-MISS] No match for definition subject: '{definition_subject}'")

    # --- 0d. DIRECT CONSERVATION TIPS ---
    if any(phrase in user_input for phrase in ["conservation tips", "conservation tip", "water saving tips", "save water"]):
        return {
            "text": f"### Conservation Tips\n\n{TIPS['conservation']}",
            "chartData": [],
            "suggestions": ["Rainwater harvesting", "What is drip irrigation?", "Show India map"],
            "skip_llm": True
        }

    # YES/NO flow
    if user_input in ["yes", "show chart", "sure", "ok"]:
        if last_data_cache["data"]:
            data = last_data_cache["data"]
            explanation = generate_data_explanation(data)
            v_type = "comparison_bars" if len(data) > 1 else "status_card"
            v_data = get_visual_data(v_type, data if len(data) > 1 else data[0])
            last_data_cache["data"] = []
            return {
                "text": f"Here's a visual breakdown of the data:\n\n{explanation}",
                "chartData": data,
                "visualType": v_type,
                "visualData": v_data,
                "suggestions": get_suggestions(user_input, data)
            }
        return {
            "text": "I don't have any prepared data yet.",
            "chartData": [],
            "suggestions": get_suggestions(user_input)
        }
    
    elif user_input in ["no", "n", "nope", "not now", "stop"]:
        last_data_cache["data"] = [] # Optional: clear cache if they decline
        return {
            "text": "No problem! What would you like to do next? You can ask me:\n\n"
                    "* **'Why is [State] stressed?'** to learn the causes.\n"
                    "* **'What is an aquifer?'** for a definition.\n"
                    "* **'Compare [District A] and [District B]'** for more data.",
            "chartData": [],
            "suggestions": get_suggestions(user_input)
        }

    # 3. UNIFIED SEMANTIC SEARCH (Priority 1)
    results = semantic_search.search(user_input, threshold=0.65)

    # Keyword fallback if semantic search fails or is uninitialized
    if not results:
        states_list = getattr(request.app.state, "states_list", [])
        districts_list = getattr(request.app.state, "districts_list", [])
        # Simple match
        for s in states_list:
            if s.lower() in user_input:
                results.append({"name": s, "score": 1.0})
        for d in districts_list:
            if d.lower() in user_input:
                results.append({"name": d, "score": 1.0})

    if results:
        best_match = results[0]["name"]
        match_key = best_match.lower()
        db = request.app.state.db

        # --- A. CHECK FOR TREND INTENT ---
        if detect_trend_intent(user_input):
            trend_data = None
            try:
                # In MongoDB we stored it with 'State' or 'state'
                trend_data = await db.state_trends.find_one({"$or": [{"State": match_key}, {"state": match_key}]})
            except Exception as e:
                print(f"Trend DB error: {e}")

            if trend_data:
                years = [k for k in trend_data.keys() if k.isdigit()]
                years.sort()
                values = [trend_data[y] for y in years]

                # Diagnostic logic
                first_val = values[0]
                last_val = values[-1]
                diff = last_val - first_val
                if abs(diff) < 2:
                    diagnostic = "stable"
                    explanation = f"Groundwater extraction in {best_match.title()} has remained **stable** over the last few years."
                elif diff > 0:
                    diagnostic = "worsening"
                    explanation = f"Groundwater extraction in {best_match.title()} is **worsening**, increasing from {first_val}% to {last_val}%."
                else:
                    diagnostic = "improving"
                    explanation = f"Groundwater extraction in {best_match.title()} is **improving**, decreasing from {first_val}% to {last_val}%."

                return {
                    "text": f"### Trend Analysis for {best_match.title()}\n\n{explanation}\n\nBased on CGWB assessment data, here is how the extraction percentage has changed over time.",
                    "chartData": [],
                    "visualType": "trend_line",
                    "visualData": {
                        "name": best_match.title(),
                        "labels": years,
                        "values": values,
                        "diagnostic": diagnostic
                    },
                    "suggestions": get_suggestions(user_input)
                }

        # --- B. CHECK FOR "WHY" / CAUSE INTENT ---
        # Ensures "Why is Punjab stressed?" returns an explanation, not just data.
        if detect_cause_intent(user_input):
            cause_text = WHY_MAP.get(match_key, "Groundwater stress in this region is typically driven by high agricultural demand (especially for water-intensive crops like paddy or sugarcane), industrial usage, and rapid urbanization that reduces natural recharge.")
            img_url = await run_in_threadpool(get_image_url, f"{best_match} groundwater stress") if is_map_requested else None
            return {
                "text": f"### Why is **{best_match.title()}** stressed?\n\n{cause_text}",
                "chartData": [],
                "imageUrl": img_url,
                "showLegend": True if img_url else False,
                "suggestions": get_suggestions(user_input)
            }

        # --- B. CHECK CONSERVATION TIPS ---
        if match_key in TIPS:
            img_url = await run_in_threadpool(get_image_url, best_match) if is_map_requested else None
            return {
                "text": f"### {best_match.title()} Tip\n\n{TIPS[match_key]}",
                "chartData": [],
                "imageUrl": img_url,
                "suggestions": get_suggestions(user_input)
            }

        # --- C. CHECK FOR ACTION/SOLUTION INTENT ---
        if detect_action_intent(user_input):
            text = (
                f"### Practical Solutions for **{best_match.title()}**\n\n"
                f"To reduce groundwater extraction and improve sustainability, consider these practical steps:\n\n"
                f"**For Households:**\n"
                f"• Install low-flow fixtures and dual-flush toilets.\n"
                f"• Harvest rooftop rainwater for non-potable use.\n"
                f"• Fix all leaks in pipes and faucets immediately.\n\n"
                f"**For Farming:**\n"
                f"• Switch to drip or sprinkler irrigation systems.\n"
                f"• Grow climate-resilient crops like millets and pulses.\n"
                f"• Use organic mulching to retain soil moisture.\n\n"
                f"**For the Community:**\n"
                f"Check dams, percolation tanks, and participating in local Water User Associations are highly effective."
            )

            img_url = await run_in_threadpool(get_image_url, f"{best_match} water conservation") if is_map_requested else None
            return {
                "text": text,
                "chartData": [],
                "imageUrl": img_url,
                "suggestions": get_suggestions(user_input)
            }

        # --- D. CHECK KNOWLEDGE BASE (Definitions) ---
        if match_key in KNOWLEDGE_BASE:
            print(f"[KB-HIT] Semantic→KB match: '{match_key}' found in KNOWLEDGE_BASE")
            img_url = await run_in_threadpool(get_image_url, best_match) if is_map_requested else None
            layered_text = format_layered_response(best_match, KNOWLEDGE_BASE[match_key])
            return {
                "text": f"### {best_match.title()}\n\n{layered_text}",
                "chartData": [],
                "imageUrl": img_url,
                "suggestions": get_suggestions(user_input),
                "skip_llm": True
            }

        # 5. Data Lookup: Location (Priority 3)
        found_data = []
        try:
            assessments_coll = db.assessments
            sample = await assessments_coll.find_one()
            if sample:
                cols = list(sample.keys())
                state_col = next((c for c in cols if "state" in c.lower()), "state")
                dist_col = next((c for c in cols if "district" in c.lower()), "district_name")
                block_col = next((c for c in cols if "block" in c.lower() or "taluka" in c.lower()), "block_name")
                extract_col = next((c for c in cols if "extraction" in c.lower() or "stage" in c.lower()), "extraction")

                states_list = getattr(request.app.state, "states_list", [])
                districts_list = getattr(request.app.state, "districts_list", [])
                states_map = {s.lower(): s for s in states_list}
                districts_map = {d.lower(): d for d in districts_list}

                seen = set()
                for res in results:
                    name = res["name"]
                    name_low = name.lower()
                    if name_low in seen: continue
                    seen.add(name_low)

                    if name_low in states_map:
                        pipeline = [
                            {"$match": {state_col: states_map[name_low]}},
                            {"$group": {"_id": None, "avg_extraction": {"$avg": f"${extract_col}"}}}
                        ]
                        agg_res = await assessments_coll.aggregate(pipeline).to_list(1)
                        val = agg_res[0]["avg_extraction"] if agg_res else None
                    elif name_low in districts_map:
                        pipeline = [
                            {"$match": {dist_col: districts_map[name_low]}},
                            {"$group": {"_id": None, "avg_extraction": {"$avg": f"${extract_col}"}}}
                        ]
                        agg_res = await assessments_coll.aggregate(pipeline).to_list(1)
                        val = agg_res[0]["avg_extraction"] if agg_res else None
                    elif name_low in KNOWLEDGE_BASE or name_low in TIPS or name_low in WHY_MAP:
                        continue
                    else:
                        doc = await assessments_coll.find_one({block_col: name})
                        val = doc.get(extract_col) if doc else None

                    if val is not None:
                        found_data.append({"name": name, "extraction": round(float(val), 2)})

                    if len(found_data) >= 5: break

            if found_data:
                last_data_cache["data"] = found_data

                unified_responses = []
                for d in found_data:
                    name_lower = d["name"].lower()

                    # 1. Extraction Explanation (Layered)
                    explanation = explain_extraction(d["name"], d["extraction"])

                    # 2. Root Causes from WHY_MAP
                    cause_text = ""
                    if name_lower in WHY_MAP:
                        cause_text = f"\n\n**Root Causes:** {WHY_MAP[name_lower]}"

                    # 3. Contaminant Warnings
                    contaminant_text = ""
                    if name_lower in CONTAMINANT_DATA:
                        cons = ", ".join(CONTAMINANT_DATA[name_lower])
                        contaminant_text = f"\n\n**Note:** {d['name']} has reported high levels of {cons}."

                    unified_responses.append(f"### {d['name'].title()}\n{explanation}{cause_text}{contaminant_text}")

                full_response = "\n\n---\n\n".join(unified_responses)
                intro = "Groundwater extraction measures usage relative to natural recharge.\n\n" if is_usage_query else ""

                # Fetch image for the locations found
                img_url = None
                if is_map_requested:
                    if len(found_data) > 1:
                        # Comparison query for multiple states/districts
                        names = [d['name'] for d in found_data]
                        img_query = f"{' and '.join(names[:2])} groundwater depth comparison map"
                    else:
                        img_query = f"{found_data[0]['name']} groundwater depth map district wise"
                    img_url = await run_in_threadpool(get_image_url, img_query)

                v_type = "comparison_bars" if len(found_data) > 1 else "status_card"
                v_data = get_visual_data(v_type, found_data if len(found_data) > 1 else found_data[0])

                # Override with risk_alert if it's a single location and has contaminants
                if len(found_data) == 1 and found_data[0]["name"].lower() in CONTAMINANT_DATA:
                    v_type = "risk_alert"
                    v_data = get_visual_data("risk_alert", CONTAMINANT_DATA[found_data[0]["name"].lower()])

                return {
                    "text": f"{intro}{full_response}\n\nWould you like a chart? (Yes/No)",
                    "chartData": [],
                    "visualType": v_type,
                    "visualData": v_data,
                    "imageUrl": img_url,
                    "showLegend": True if img_url else False,
                    "suggestions": get_suggestions(user_input, found_data)
                }

        except Exception as e:
            return {"text": f"Database error: {str(e)}", "chartData": [], "suggestions": get_suggestions(user_input)}

        # Fallback for WHY_MAP if "why" wasn't in query but it's the best match and not a location
        if match_key in WHY_MAP:
            img_url = await run_in_threadpool(get_image_url, f"{best_match} groundwater stress") if is_map_requested else None
            return {
                "text": f"### Why is **{best_match.title()}** stressed?\n\n{WHY_MAP[match_key]}",
                "chartData": [],
                "imageUrl": img_url,
                "suggestions": get_suggestions(user_input)
            }

    # 6. FUZZY FALLBACK: Try matching against knowledge base / tips with typo tolerance
    fuzzy_kb_key = fuzzy_match_key(user_input, KNOWLEDGE_BASE, threshold=0.50)
    if fuzzy_kb_key:
        print(f"[FUZZY-HIT] Fallback fuzzy KB match: '{user_input}' -> '{fuzzy_kb_key}'")
        layered_text = format_layered_response(fuzzy_kb_key, KNOWLEDGE_BASE[fuzzy_kb_key])
        return {
            "text": f"### {fuzzy_kb_key.title()}\n\n{layered_text}",
            "chartData": [],
            "suggestions": get_suggestions(user_input),
            "skip_llm": True
        }

    fuzzy_tip_key = fuzzy_match_key(user_input, TIPS, threshold=0.50)
    if fuzzy_tip_key:
        print(f"[FUZZY-HIT] Fallback fuzzy TIPS match: '{user_input}' -> '{fuzzy_tip_key}'")
        return {
            "text": f"### {fuzzy_tip_key.title()} Tip\n\n{TIPS[fuzzy_tip_key]}",
            "chartData": [],
            "suggestions": get_suggestions(user_input),
            "skip_llm": True
        }

    # 7. News Fallback (Priority 5)
    news = await run_in_threadpool(get_latest_news)
    news_str = "\n".join([f"• {item}" for item in news])
    return {
        "text": f"I couldn't find specific data for your query, but here are the latest groundwater updates:\n\n{news_str}\n\n💡 **Tip:** Try asking me specific questions like:\n• 'What is groundwater?'\n• 'Compare Punjab and Bihar'\n• 'Why is Rajasthan stressed?'\n• 'Conservation tips'",
        "chartData": [],
        "suggestions": ["What is groundwater?", "Conservation tips", "Show India map"]
    }

@app.post("/ask")
async def ask_bot(item: WaterQuery, request: Request):
    user_input = item.message.strip().lower()

    # 1. Get verified context and base response from rule-based engine
    base_response = await get_rule_based_response(user_input, request)
    context = base_response.get("text", "")

    if item.stream:
        # Skip LLM for direct responses (greetings, thanks, bye)
        if base_response.get("skip_llm"):
            async def direct_stream():
                for ch in context:
                    yield f"data: {json.dumps({'t': ch})}\n\n"
                    await asyncio.sleep(0.008)
                metadata = {
                    "visualType": base_response.get("visualType"),
                    "visualData": base_response.get("visualData"),
                    "chartData": base_response.get("chartData"),
                    "imageUrl": base_response.get("imageUrl"),
                    "showLegend": base_response.get("showLegend"),
                    "suggestions": base_response.get("suggestions")
                }
                yield f"data: {json.dumps({'m': metadata})}\n\n"
            return StreamingResponse(direct_stream(), media_type="text/event-stream")
        async def stream_generator():
            full_text = ""
            try:
                # 2. Get smart response from LLM with timeout to prevent infinite hangs
                async def consume_llm():
                    nonlocal full_text
                    async for ch in get_smart_response(item.message, context):
                        full_text += ch
                        yield ch

                try:
                    llm_gen = consume_llm()
                    # Use a manual timeout: read chunks with a per-iteration deadline
                    start_time = time.monotonic()
                    LLM_TIMEOUT = 30  # seconds
                    async for ch in llm_gen:
                        yield f"data: {json.dumps({'t': ch})}\n\n"
                        if time.monotonic() - start_time > LLM_TIMEOUT:
                            print("[TIMEOUT] LLM streaming exceeded 30s, falling back")
                            break
                except asyncio.TimeoutError:
                    print("[TIMEOUT] LLM call timed out after 30s")
                except Exception as e:
                    print(f"Streaming error: {e}")
            except Exception as e:
                print(f"Outer streaming error: {e}")

            # 3. Reliability & Fallback
            if not full_text:
                # If LLM failed, yield base response text in characters
                for ch in context:
                    yield f"data: {json.dumps({'t': ch})}\n\n"
                    await asyncio.sleep(0.008)

            # 4. Final metadata for visual components
            metadata = {
                "visualType": base_response.get("visualType"),
                "visualData": base_response.get("visualData"),
                "chartData": base_response.get("chartData"),
                "imageUrl": base_response.get("imageUrl"),
                "showLegend": base_response.get("showLegend"),
                "suggestions": base_response.get("suggestions")
            }
            yield f"data: {json.dumps({'m': metadata})}\n\n"

        return StreamingResponse(stream_generator(), media_type="text/event-stream")

    else:
        # Non-streaming path
        # Skip LLM for direct responses (greetings, thanks, bye)
        if base_response.get("skip_llm"):
            return base_response

        full_text = ""
        try:
            async for token in get_smart_response(item.message, context):
                full_text += token
        except Exception as e:
            print(f"LLM Error: {e}")

        # Fallback to rule-based text if LLM fails or returns empty
        if full_text.strip():
            base_response["text"] = full_text

        # SAFETY: Ensure we never return an empty response
        if not base_response.get("text", "").strip():
            base_response["text"] = (
                "I'm sorry, I couldn't generate a response for that query. "
                "Please try rephrasing your question, or ask me about:\n\n"
                "• Groundwater levels in any Indian state\n"
                "• Water-related definitions (e.g., 'What is an aquifer?')\n"
                "• Conservation tips and solutions"
            )
            base_response["suggestions"] = ["What is groundwater?", "Conservation tips", "Show India map"]

        return base_response

@app.get("/get-news")
async def get_news():
    """Returns top 3 groundwater news headlines."""
    news = await run_in_threadpool(get_latest_news)
    return {"news": news}

@app.get("/health")
def read_root():
    return {
        "status": "Online",
        "message": "INGRES AI Groundwater API is running",
        "endpoints": {
            "ask": "/ask (POST)",
            "get-news": "/get-news (GET)",
            "health": "/health (GET)",
            "ml": "/api/ml/* (GET/POST)"
        }
    }

# -------------------- STATIC FILES (PRODUCTION) --------------------
STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "Frontend", "dist")
if os.path.exists(STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")

    @app.get("/")
    def serve_frontend():
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        file_path = os.path.join(STATIC_DIR, full_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
else:
    @app.get("/")
    def serve_dev():
        return {"status": "Online", "message": "INGRES API — frontend not built yet. Run: cd Frontend && npm run build"}
