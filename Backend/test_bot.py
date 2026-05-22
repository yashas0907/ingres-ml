import pytest
from fastapi.testclient import TestClient
import sys
import os
from unittest.mock import patch, AsyncMock, MagicMock
import asyncio

# Add the current directory to sys.path to allow importing Backend.main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set dummy HF_TOKEN for tests
os.environ["HF_TOKEN"] = "dummy"

from Backend.main import app, KNOWLEDGE_BASE, TIPS, WHY_MAP

@pytest.fixture(autouse=True)
def mock_genai():
    with patch("Backend.main.get_smart_response") as mock:
        async def side_effect(query, context):
            for ch in context:
                yield ch
        mock.side_effect = side_effect
        yield mock

@pytest.fixture(autouse=True)
def mock_mongo():
    with patch("motor.motor_asyncio.AsyncIOMotorClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_db = MagicMock()
        mock_client.__getitem__.return_value = mock_db

        # Mock assessments collection
        mock_assessments = MagicMock()
        mock_db.assessments = mock_assessments

        # Mock state_trends collection
        mock_state_trends = MagicMock()
        mock_db.state_trends = mock_state_trends

        # Mock find_one for lifespan and others
        mock_assessments.find_one = AsyncMock(return_value={
            "state": "Karnataka", "district_name": "Bangalore", "block_name": "North", "extraction": 90.0, "category": "Stressed"
        })

        # Mock distinct for lifespan
        mock_assessments.distinct = AsyncMock(side_effect=lambda col: {
            "state": ["Karnataka", "Punjab", "Bihar"],
            "district_name": ["Bangalore", "Amritsar", "Patna"],
            "block_name": ["North", "Central", "South"]
        }.get(col, []))

        yield {
            "client": mock_client,
            "db": mock_db,
            "assessments": mock_assessments,
            "state_trends": mock_state_trends
        }

@patch('Backend.main.semantic_search.search')
def test_knowledge_base_query(mock_search):
    mock_search.return_value = [{"name": "aquifer", "score": 0.9}]
    with TestClient(app) as client:
        # Semantic search for a knowledge base key
        response = client.post("/ask", json={"message": "aquifer"})
        assert response.status_code == 200
        data = response.json()
        assert "aquifer" in data["text"].lower()
        assert KNOWLEDGE_BASE["aquifer"] in data["text"]

@patch('Backend.main.semantic_search.search')
def test_location_query(mock_search, mock_mongo):
    mock_search.return_value = [{"name": "Karnataka", "score": 0.9}]

    mock_assessments = mock_mongo["assessments"]
    # Mock aggregation for average extraction
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[{"avg_extraction": 90.0}])
    mock_assessments.aggregate.return_value = mock_cursor

    with TestClient(app) as client:
        # Semantic search for a location
        response = client.post("/ask", json={"message": "Karnataka"})
        assert response.status_code == 200
        data = response.json()
        assert "Karnataka" in data["text"]
        assert "extraction" in data["text"].lower()

@patch('Backend.main.semantic_search.search')
def test_news_fallback(mock_search):
    mock_search.return_value = []
    with TestClient(app) as client:
        # Query that should have low confidence (< 0.65)
        response = client.post("/ask", json={"message": "Who won the world cup?"})
        assert response.status_code == 200
        data = response.json()
        assert "latest groundwater updates" in data["text"].lower()

@patch('Backend.main.semantic_search.search')
def test_why_query(mock_search):
    mock_search.return_value = [{"name": "punjab", "score": 0.9}]
    with TestClient(app) as client:
        # "Why" query matching WHY_MAP
        response = client.post("/ask", json={"message": "why Punjab"})
        assert response.status_code == 200
        data = response.json()
        assert "Punjab" in data["text"]
        assert WHY_MAP["punjab"] in data["text"]

@patch('Backend.main.semantic_search.search')
def test_master_plan_query(mock_search):
    mock_search.return_value = [{"name": "master plan", "score": 0.9}]
    with TestClient(app) as client:
        # Query for one of the newly added 50 QA pairs
        response = client.post("/ask", json={"message": "master plan"})
        assert response.status_code == 200
        data = response.json()
        assert "Master Plan" in data["text"]
        assert "1.42 crore" in data["text"]

@patch('Backend.main.semantic_search.search')
@patch('Backend.main.get_image_url')
def test_map_suppression(mock_get_image, mock_search, mock_mongo):
    mock_search.return_value = [{"name": "Karnataka", "score": 0.9}]
    mock_get_image.return_value = "http://map.url"

    mock_assessments = mock_mongo["assessments"]
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[{"avg_extraction": 90.0}])
    mock_assessments.aggregate.return_value = mock_cursor

    with TestClient(app) as client:
        # Normal query should NOT have imageUrl
        response = client.post("/ask", json={"message": "Karnataka"})
        data = response.json()
        assert data.get("imageUrl") is None

        # Query with "map" should have imageUrl
        response = client.post("/ask", json={"message": "show map for Karnataka"})
        data = response.json()
        assert data.get("imageUrl") == "http://map.url"

@patch('Backend.main.semantic_search.search')
def test_visual_types(mock_search, mock_mongo):
    mock_assessments = mock_mongo["assessments"]

    # Mock aggregation for average extraction
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[{"avg_extraction": 90.0}])
    mock_assessments.aggregate.return_value = mock_cursor

    with TestClient(app) as client:
        # Single location -> status_card (or risk_alert if contaminants exist)
        mock_search.return_value = [{"name": "Karnataka", "score": 0.9}]
        response = client.post("/ask", json={"message": "Karnataka"})
        data = response.json()
        # Karnataka has contaminants in CONTAMINANT_DATA, so should be risk_alert
        assert data.get("visualType") == "risk_alert"
        assert "contaminantList" in data["visualData"]

        # Multiple locations -> comparison_bars
        mock_search.return_value = [
            {"name": "Punjab", "score": 0.9},
            {"name": "Bihar", "score": 0.8}
        ]
        response = client.post("/ask", json={"message": "compare Punjab and Bihar"})
        data = response.json()
        assert data.get("visualType") == "comparison_bars"
        assert len(data["visualData"]) >= 2

@patch('Backend.main.semantic_search.search')
def test_trend_query(mock_search, mock_mongo):
    mock_search.return_value = [{"name": "Punjab", "score": 0.9}]

    mock_state_trends = mock_mongo["state_trends"]
    mock_state_trends.find_one = AsyncMock(return_value={
        "State": "punjab", "2017": 149, "2020": 150, "2022": 145
    })

    with TestClient(app) as client:
        # Query for trend
        response = client.post("/ask", json={"message": "show trend for Punjab"})
        assert response.status_code == 200
        data = response.json()
        assert data.get("visualType") == "trend_line"
        assert "labels" in data["visualData"]
        assert "values" in data["visualData"]
        assert "diagnostic" in data["visualData"]
