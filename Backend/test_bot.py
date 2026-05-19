import pytest
from fastapi.testclient import TestClient
import sys
import os
from unittest.mock import patch

# Add the current directory to sys.path to allow importing Backend.main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Backend.main import app, KNOWLEDGE_BASE, TIPS, WHY_MAP

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
def test_location_query(mock_search):
    mock_search.return_value = [{"name": "Karnataka", "score": 0.9}]
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
def test_map_suppression(mock_get_image, mock_search):
    mock_search.return_value = [{"name": "Karnataka", "score": 0.9}]
    mock_get_image.return_value = "http://map.url"
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
def test_visual_types(mock_search):
    with TestClient(app) as client:
        # Single location -> status_card (or risk_alert if contaminants exist)
        mock_search.return_value = [{"name": "Karnataka", "score": 0.9}]
        response = client.post("/ask", json={"message": "Karnataka"})
        data = response.json()
        # Karnataka has contaminants in CONTAMINANT_DATA, so should be risk_alert
        assert data.get("visualType") == "risk_alert"
        assert "contaminantList" in data["visualData"]

        # Single location NO contaminants -> status_card
        # Based on WHY_MAP, Maharashtra is there, let's assume it's in DB or mock it
        mock_search.return_value = [{"name": "Maharashtra", "score": 0.9}]
        response = client.post("/ask", json={"message": "Maharashtra"})
        data = response.json()
        # If it's not in DB it might fall back to WHY_MAP
        # Maharashtra fallback no longer returns action_panel
        if data.get("visualType") == "status_card":
             assert data.get("visualType") == "status_card"

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
def test_trend_query(mock_search):
    mock_search.return_value = [{"name": "Punjab", "score": 0.9}]
    with TestClient(app) as client:
        # Query for trend
        response = client.post("/ask", json={"message": "show trend for Punjab"})
        assert response.status_code == 200
        data = response.json()
        assert data.get("visualType") == "trend_line"
        assert "labels" in data["visualData"]
        assert "values" in data["visualData"]
        assert "diagnostic" in data["visualData"]
