import os
import json
import csv
from datetime import datetime
from typing import Dict, List, Any
import uuid

from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel

# Create necessary directories
os.makedirs("static", exist_ok=True)
os.makedirs("static/uploads", exist_ok=True)
os.makedirs("templates", exist_ok=True)

# File paths
CATALOG_FILE = "catalog.json"
UPLOADS_DIR = "static/uploads"

# Initialize FastAPI app
app = FastAPI()

# Add session middleware (using env var for security)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "temp-secret-key")  # Set in Render dashboard
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize templates
templates = Jinja2Templates(directory="templates")

# Health check endpoint (for Render)
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# HEAD method handler for root
@app.head("/")
async def head_root():
    return Response("")

# Data model
class Product(BaseModel):
    title: str
    description: str
    price: float
    cost: float
    image_url: str
    timestamp: str
    predicted_profit_margin: float

# Helper functions
def load_catalog() -> List[Dict[str, Any]]:
    if os.path.exists(CATALOG_FILE):
        with open(CATALOG_FILE, 'r') as f:
            return json.load(f)
    return []

def save_catalog(catalog: List[Dict[str, Any]]) -> None:
    with open(CATALOG_FILE, 'w') as f:
        json.dump(catalog, f, indent=2)

def calculate_profit_margin(price: float, cost: float) -> float:
    if price <= 0:
        return 0.0
    return round(((price - cost) / price) * 100, 2)

# Routes
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Main page with product form and login widget placeholder"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/debug", response_class=HTMLResponse)
async def debug():
    """Debug page to test routing"""
    return """
    <html>
        <head><title>Debug Page</title></head>
        <body>
            <h1>Debug Page</h1>
            <p>If you can see this, the FastAPI app is working correctly.</p>
            <p><a href="/">Go to home</a></p>
            <p><a href="/catalog_ui">Go to catalog</a></p>
        </body>
    </html>
    """

@app.post("/add_product")
async def add_product(
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    price: float = Form(...),
    cost: float = Form(...),
    image: UploadFile = File(...)
):
    """Add a new product to the catalog"""
    try:
        image_filename = f"{uuid.uuid4()}{os.path.splitext(image.filename)[1]}"
        image_path = os.path.join(UPLOADS_DIR, image_filename)
        with open(image_path, "wb") as f:
            f.write(await image.read())
        image_url = f"/static/uploads/{image_filename}"
        profit_margin = calculate_profit_margin(price, cost)
        product = {
            "title": title,
            "description": description,
            "price": price,
            "cost": cost,
            "image_url": image_url,
            "timestamp": datetime.now().isoformat(),
            "predicted_profit_margin": profit_margin
        }
        catalog = load_catalog()
        catalog.append(product)
        save_catalog(catalog)
        return RedirectResponse("/catalog_ui", status_code=303)
    except Exception as e:
        print(f"Error adding product: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error adding product: {str(e)}")

@app.get("/catalog_ui", response_class=HTMLResponse)
async def catalog_ui(request: Request):
    """Display the product catalog"""
    items = load_catalog()
    return templates.TemplateResponse("catalog.html", {"request": request, "items": items})

@app.get("/export_catalog")
async def export_catalog():
    """Export the catalog as a CSV file"""
    catalog = load_catalog()
    try:
        csv_file = "catalog_export.csv"
        with open(csv_file, mode='w', newline='') as file:
            fieldnames = ['title', 'description', 'price', 'cost', 'profit_margin', 'timestamp']
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            for item in catalog:
                writer.writerow({
                    'title': item['title'],
                    'description': item['description'],
                    'price': item['price'],
                    'cost': item.get('cost', 0),
                    'profit_margin': item['predicted_profit_margin'],
                    'timestamp': item['timestamp']
                })
        response = FileResponse(
            path=csv_file,
            filename="dropshipping_catalog.csv",
            media_type="text/csv"
        )
        # Cleanup temporary file (Render filesystem consideration)
        os.remove(csv_file)
        return response
    except Exception as e:
        print(f"Error exporting catalog: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error exporting catalog: {str(e)}")

# Start the app with Render-compatible configuration
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))  # Render default port
    uvicorn.run(app, host="0.0.0.0", port=port)
