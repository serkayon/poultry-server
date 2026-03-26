>>>>> cd backend; cd app; $env:DATABASE_URL="postgresql+psycopg://YOUR_USER:YOUR_PASSWORD@localhost:5432/poultry"; venv\Scripts\activate; uvicorn main:app --reload --host 127.0.0.1 --port 8007

>>>>> cd backend && cd hmi && venv\Scripts\activate && uvicorn app:app --reload --host 127.0.0.1 --port 8010         >>>> for hmi dashboard

>>>>> cd frontend && npm run dev                                             >>>> for poultry dashboard


