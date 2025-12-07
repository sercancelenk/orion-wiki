# backend
python -m pip install -r requirements.txt

# FastAPI
uvicorn backend.main:app --reload --port 8001

# UI
streamlit run ui/app.py