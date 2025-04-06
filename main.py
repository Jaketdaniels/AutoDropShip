import os
import json
import csv
import base64
import secrets
from datetime import datetime
from typing import Optional, Dict, List, Any
import uuid

from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.sessions import SessionMiddleware
import httpx
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# API Configuration
ETSY_CLIENT_ID = os.getenv("ETSY_CLIENT_ID", "your_etsy_client_id")
ETSY_CLIENT_SECRET = os.getenv("ETSY_CLIENT_SECRET", "your_etsy_client_secret")
ETSY_REDIRECT_URI = os.getenv("ETSY_REDIRECT_URI", "https://your-app.onrender.com/callback/etsy")

EBAY_CLIENT_ID = os.getenv("EBAY_CLIENT_ID", "your_ebay_client_id")
EBAY_CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET", "your_ebay_client_secret")
EBAY_REDIRECT_URI = os.getenv("EBAY_REDIRECT_URI", "https://your-app.onrender.com/callback/ebay")
EBAY_RU_NAME = os.getenv("EBAY_RU_NAME", "your_ebay_runame")

# File paths
CATALOG_FILE = "catalog.json"
UPLOADS_DIR = "uploads"

# Ensure uploads directory exists
os.makedirs(UPLOADS_DIR, exist_ok=True)

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", secrets.token_hex(16)))

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Data models
class Product(BaseModel):
    title: str
    description: str
    price: float
    cost: float
    image_url: str
    timestamp: str
    predicted_profit_margin: float
    published_ebay: bool = False
    published_etsy: bool = False
    ebay_listing_id: Optional[str] = None
    etsy_listing_id: Optional[str] = None

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
    return round(((price - cost) / price) * 100, 2)

# Routes
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Main page with product predictor form"""
    ebay_logged_in = request.session.get("ebay_access_token") is not None
    etsy_logged_in = request.session.get("etsy_access_token") is not None
    
    return templates.TemplateResponse(
        "index.html", 
        {
            "request": request,
            "ebay_logged_in": ebay_logged_in,
            "etsy_logged_in": etsy_logged_in
        }
    )

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
    # Save the uploaded image
    image_filename = f"{uuid.uuid4()}{os.path.splitext(image.filename)[1]}"
    image_path = os.path.join(UPLOADS_DIR, image_filename)
    
    # Create the uploads directory if it doesn't exist
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    
    # Save the file
    with open(image_path, "wb") as f:
        f.write(await image.read())
    
    # Create relative URL for the image
    image_url = f"/static/uploads/{image_filename}"
    
    # Calculate profit margin
    profit_margin = calculate_profit_margin(price, cost)
    
    # Create product entry
    product = {
        "title": title,
        "description": description,
        "price": price,
        "cost": cost,
        "image_url": image_url,
        "timestamp": datetime.now().isoformat(),
        "predicted_profit_margin": profit_margin,
        "published_ebay": False,
        "published_etsy": False
    }
    
    # Add to catalog
    catalog = load_catalog()
    catalog.append(product)
    save_catalog(catalog)
    
    return RedirectResponse("/catalog_ui", status_code=303)

@app.get("/catalog_ui", response_class=HTMLResponse)
async def catalog_ui(request: Request):
    """Display the product catalog with publishing options"""
    items = load_catalog()
    ebay_logged_in = request.session.get("ebay_access_token") is not None
    etsy_logged_in = request.session.get("etsy_access_token") is not None
    
    return templates.TemplateResponse(
        "catalog.html", 
        {
            "request": request,
            "items": items,
            "ebay_logged_in": ebay_logged_in,
            "etsy_logged_in": etsy_logged_in
        }
    )

@app.get("/export_catalog")
async def export_catalog():
    """Export the catalog as a CSV file"""
    catalog = load_catalog()
    
    # Create a temporary CSV file
    csv_file = "catalog_export.csv"
    with open(csv_file, mode='w', newline='') as file:
        fieldnames = ['title', 'description', 'price', 'cost', 'profit_margin', 
                     'timestamp', 'published_ebay', 'published_etsy']
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        
        writer.writeheader()
        for item in catalog:
            writer.writerow({
                'title': item['title'],
                'description': item['description'],
                'price': item['price'],
                'cost': item.get('cost', 0),
                'profit_margin': item['predicted_profit_margin'],
                'timestamp': item['timestamp'],
                'published_ebay': item.get('published_ebay', False),
                'published_etsy': item.get('published_etsy', False)
            })
    
    return FileResponse(
        path=csv_file, 
        filename="dropshipping_catalog.csv", 
        media_type="text/csv"
    )

# Authentication Routes
@app.get("/auth/etsy")
async def auth_etsy():
    """Initiate Etsy OAuth flow"""
    # Generate a random state for CSRF protection
    state = secrets.token_hex(16)
    
    # Build Etsy authorization URL
    scopes = "listings_r listings_w"
    auth_url = f"https://www.etsy.com/oauth/connect" \
               f"?response_type=code" \
               f"&client_id={ETSY_CLIENT_ID}" \
               f"&redirect_uri={ETSY_REDIRECT_URI}" \
               f"&scope={scopes}" \
               f"&state={state}"
    
    return RedirectResponse(auth_url)

@app.get("/callback/etsy")
async def callback_etsy(code: str, state: Optional[str] = None, request: Request = None):
    """Handle Etsy OAuth callback"""
    # Exchange code for access token
    token_url = "https://api.etsy.com/v3/public/oauth/token"
    data = {
        "grant_type": "authorization_code",
        "client_id": ETSY_CLIENT_ID,
        "redirect_uri": ETSY_REDIRECT_URI,
        "code": code
    }
    
    auth_str = f"{ETSY_CLIENT_ID}:{ETSY_CLIENT_SECRET}"
    auth_bytes = auth_str.encode('ascii')
    auth_header = base64.b64encode(auth_bytes).decode('ascii')
    
    headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(token_url, data=data, headers=headers)
            token_data = response.json()
            
            if response.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to obtain Etsy access token")
            
            # Store tokens in session
            request.session["etsy_access_token"] = token_data["access_token"]
            request.session["etsy_refresh_token"] = token_data.get("refresh_token")
            request.session["etsy_token_expiry"] = datetime.now().timestamp() + token_data["expires_in"]
            
            # Get shop info
            shop_url = "https://openapi.etsy.com/v3/application/shops"
            shop_headers = {
                "Authorization": f"Bearer {token_data['access_token']}",
                "x-api-key": ETSY_CLIENT_ID
            }
            
            shop_response = await client.get(shop_url, headers=shop_headers)
            if shop_response.status_code == 200:
                shop_data = shop_response.json()
                request.session["etsy_shop_id"] = shop_data["shop_id"]
                request.session["etsy_shop_name"] = shop_data["shop_name"]
    except Exception as e:
        print(f"Etsy authentication error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Etsy authentication error: {str(e)}")
    
    return RedirectResponse("/catalog_ui")

@app.get("/auth/ebay")
async def auth_ebay():
    """Initiate eBay OAuth flow"""
    # Generate a random state for CSRF protection
    state = secrets.token_hex(16)
    
    # Build eBay authorization URL
    scopes = "https://api.ebay.com/oauth/api_scope https://api.ebay.com/oauth/api_scope/sell.inventory https://api.ebay.com/oauth/api_scope/sell.marketing"
    
    # For production
    # auth_url = f"https://auth.ebay.com/oauth2/authorize"
    # For sandbox
    auth_url = f"https://auth.sandbox.ebay.com/oauth2/authorize" \
               f"?client_id={EBAY_CLIENT_ID}" \
               f"&response_type=code" \
               f"&redirect_uri={EBAY_REDIRECT_URI}" \
               f"&scope={scopes}" \
               f"&state={state}"
    
    return RedirectResponse(auth_url)

@app.get("/callback/ebay")
async def callback_ebay(code: str, state: Optional[str] = None, request: Request = None):
    """Handle eBay OAuth callback"""
    # Exchange code for access token
    # token_url = "https://api.ebay.com/identity/v1/oauth2/token"  # Production
    token_url = "https://api.sandbox.ebay.com/identity/v1/oauth2/token"  # Sandbox
    
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": EBAY_REDIRECT_URI
    }
    
    auth_str = f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}"
    auth_bytes = auth_str.encode('ascii')
    auth_header = base64.b64encode(auth_bytes).decode('ascii')
    
    headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(token_url, data=data, headers=headers)
            token_data = response.json()
            
            if response.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to obtain eBay access token")
            
            # Store tokens in session
            request.session["ebay_access_token"] = token_data["access_token"]
            request.session["ebay_refresh_token"] = token_data.get("refresh_token")
            request.session["ebay_token_expiry"] = datetime.now().timestamp() + token_data["expires_in"]
    except Exception as e:
        print(f"eBay authentication error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"eBay authentication error: {str(e)}")
    
    return RedirectResponse("/catalog_ui")

# Publishing Routes
@app.get("/publish/ebay/{item_id}")
async def publish_ebay(item_id: int, request: Request):
    """Publish a product to eBay"""
    access_token = request.session.get("ebay_access_token")
    if not access_token:
        return RedirectResponse("/auth/ebay")
    
    catalog = load_catalog()
    if item_id >= len(catalog):
        raise HTTPException(status_code=404, detail="Item not found")

    item = catalog[item_id]
    
    # Check if token is expired and refresh if needed
    if datetime.now().timestamp() > request.session.get("ebay_token_expiry", 0):
        await refresh_ebay_token(request)
        access_token = request.session.get("ebay_access_token")
    
    try:
        # Create eBay inventory item
        inventory_api_url = "https://api.sandbox.ebay.com/sell/inventory/v1/inventory_item"
        sku = f"DROPSHIP-{uuid.uuid4()}"
        
        inventory_payload = {
            "availability": {
                "shipToLocationAvailability": {
                    "quantity": 10
                }
            },
            "condition": "NEW",
            "product": {
                "title": item["title"],
                "description": item["description"],
                "aspects": {},
                "imageUrls": [item["image_url"]]
            }
        }
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Content-Language": "en-US"
        }
        
        async with httpx.AsyncClient() as client:
            # Create inventory item
            inv_response = await client.put(
                f"{inventory_api_url}/{sku}",
                json=inventory_payload,
                headers=headers
            )
            
            if inv_response.status_code not in (200, 201, 204):
                print(f"eBay inventory error: {inv_response.text}")
                raise HTTPException(status_code=500, detail="Failed to create eBay inventory item")
            
            # Create offer
            offer_api_url = "https://api.sandbox.ebay.com/sell/inventory/v1/offer"
            offer_payload = {
                "sku": sku,
                "marketplaceId": "EBAY_US",
                "format": "FIXED_PRICE",
                "availableQuantity": 10,
                "categoryId": "9355",  # General category, should be adjusted for real products
                "listingDescription": item["description"],
                "listingPolicies": {
                    "fulfillmentPolicies": [
                        {
                            "fulfillmentPolicyId": "123456789"  # Should be replaced with actual policy ID
                        }
                    ],
                    "paymentPolicies": [
                        {
                            "paymentPolicyId": "123456789"  # Should be replaced with actual policy ID
                        }
                    ],
                    "returnPolicies": [
                        {
                            "returnPolicyId": "123456789"  # Should be replaced with actual policy ID
                        }
                    ]
                },
                "pricingSummary": {
                    "price": {
                        "value": str(item["price"]),
                        "currency": "USD"
                    }
                }
            }
            
            offer_response = await client.post(
                offer_api_url,
                json=offer_payload,
                headers=headers
            )
            
            if offer_response.status_code not in (200, 201):
                print(f"eBay offer error: {offer_response.text}")
                raise HTTPException(status_code=500, detail="Failed to create eBay offer")
            
            offer_data = offer_response.json()
            offer_id = offer_data.get("offerId")
            
            # Publish the offer
            publish_url = f"https://api.sandbox.ebay.com/sell/inventory/v1/offer/{offer_id}/publish"
            publish_response = await client.post(publish_url, headers=headers)
            
            if publish_response.status_code not in (200, 201):
                print(f"eBay publish error: {publish_response.text}")
                raise HTTPException(status_code=500, detail="Failed to publish eBay listing")
            
            publish_data = publish_response.json()
            listing_id = publish_data.get("listingId")
            
            # Update catalog with listing info
            item["published_ebay"] = True
            item["ebay_listing_id"] = listing_id
            save_catalog(catalog)
            
    except Exception as e:
        print(f"eBay publishing error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"eBay publishing error: {str(e)}")

    return RedirectResponse("/catalog_ui")

@app.get("/publish/etsy/{item_id}")
async def publish_etsy(item_id: int, request: Request):
    """Publish a product to Etsy"""
    access_token = request.session.get("etsy_access_token")
    if not access_token:
        return RedirectResponse("/auth/etsy")
    
    catalog = load_catalog()
    if item_id >= len(catalog):
        raise HTTPException(status_code=404, detail="Item not found")

    item = catalog[item_id]
    shop_id = request.session.get("etsy_shop_id")
    
    # Check if token is expired and refresh if needed
    if datetime.now().timestamp() > request.session.get("etsy_token_expiry", 0):
        await refresh_etsy_token(request)
        access_token = request.session.get("etsy_access_token")
    
    try:
        # Create Etsy listing
        listing_api_url = f"https://openapi.etsy.com/v3/application/shops/{shop_id}/listings"
        
        listing_payload = {
            "quantity": 10,
            "title": item["title"],
            "description": item["description"],
            "price": item["price"],
            "who_made": "someone_else",
            "is_supply": True,
            "when_made": "2020_2023",
            "taxonomy_id": 1,  # Should be replaced with appropriate taxonomy ID
            "shipping_profile_id": 123456  # Should be replaced with actual shipping profile ID
        }
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "x-api-key": ETSY_CLIENT_ID
        }
        
        async with httpx.AsyncClient() as client:
            # Create listing
            listing_response = await client.post(
                listing_api_url,
                json=listing_payload,
                headers=headers
            )
            
            if listing_response.status_code not in (200, 201):
                print(f"Etsy listing error: {listing_response.text}")
                raise HTTPException(status_code=500, detail="Failed to create Etsy listing")
            
            listing_data = listing_response.json()
            listing_id = listing_data.get("listing_id")
            
            # Upload image
            image_url = item["image_url"]
            if image_url.startswith("/static/uploads/"):
                image_path = os.path.join("static", "uploads", os.path.basename(image_url))
                
                with open(image_path, "rb") as image_file:
                    image_upload_url = f"https://openapi.etsy.com/v3/application/shops/{shop_id}/listings/{listing_id}/images"
                    files = {"image": image_file}
                    
                    image_response = await client.post(
                        image_upload_url,
                        files=files,
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "x-api-key": ETSY_CLIENT_ID
                        }
                    )
                    
                    if image_response.status_code not in (200, 201):
                        print(f"Etsy image upload error: {image_response.text}")
                        # Continue anyway, listing was created
            
            # Update catalog with listing info
            item["published_etsy"] = True
            item["etsy_listing_id"] = str(listing_id)
            save_catalog(catalog)
            
    except Exception as e:
        print(f"Etsy publishing error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Etsy publishing error: {str(e)}")

    return RedirectResponse("/catalog_ui")

# Token refresh functions
async def refresh_ebay_token(request: Request):
    """Refresh eBay access token"""
    refresh_token = request.session.get("ebay_refresh_token")
    if not refresh_token:
        return RedirectResponse("/auth/ebay")
    
    token_url = "https://api.sandbox.ebay.com/identity/v1/oauth2/token"
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    
    auth_str = f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}"
    auth_bytes = auth_str.encode('ascii')
    auth_header = base64.b64encode(auth_bytes).decode('ascii')
    
    headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(token_url, data=data, headers=headers)
            token_data = response.json()
            
            if response.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to refresh eBay token")
            
            # Update tokens in session
            request.session["ebay_access_token"] = token_data["access_token"]
            request.session["ebay_token_expiry"] = datetime.now().timestamp() + token_data["expires_in"]
            if "refresh_token" in token_data:
                request.session["ebay_refresh_token"] = token_data["refresh_token"]
                
    except Exception as e:
        print(f"eBay token refresh error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"eBay token refresh error: {str(e)}")

async def refresh_etsy_token(request: Request):
    """Refresh Etsy access token"""
    refresh_token = request.session.get("etsy_refresh_token")
    if not refresh_token:
        return RedirectResponse("/auth/etsy")
    
    token_url = "https://api.etsy.com/v3/public/oauth/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": ETSY_CLIENT_ID,
        "refresh_token": refresh_token
    }
    
    auth_str = f"{ETSY_CLIENT_ID}:{ETSY_CLIENT_SECRET}"
    auth_bytes = auth_str.encode('ascii')
    auth_header = base64.b64encode(auth_bytes).decode('ascii')
    
    headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(token_url, data=data, headers=headers)
            token_data = response.json()
            
            if response.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to refresh Etsy token")
            
            # Update tokens in session
            request.session["etsy_access_token"] = token_data["access_token"]
            request.session["etsy_token_expiry"] = datetime.now().timestamp() + token_data["expires_in"]
            if "refresh_token" in token_data:
                request.session["etsy_refresh_token"] = token_data["refresh_token"]
                
    except Exception as e:
        print(f"Etsy token refresh error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Etsy token refresh error: {str(e)}")

# Start the app
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
