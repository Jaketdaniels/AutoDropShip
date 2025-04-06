# Dropshipping Platform

A fully-featured dropshipping application that integrates with eBay and Etsy APIs to automate product listing.

## Features

- Product catalog management
- Profit margin calculation
- Authentication with eBay and Etsy
- Direct publishing to marketplace platforms
- Export catalog as CSV

## Setup

### Prerequisites

- Python 3.8+
- eBay Developer Account
- Etsy Developer Account

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/dropshipping-platform.git
cd dropshipping-platform
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment variables:
```bash
cp .env.example .env
```
Edit the `.env` file with your API keys and settings.

5. Run the application:
```bash
uvicorn main:app --reload
```

## API Configuration

### eBay API Setup

1. Register as an eBay developer: https://developer.ebay.com/
2. Create a new application
3. Generate OAuth credentials
4. Configure the redirect URI to match your application URL + `/callback/ebay`

### Etsy API Setup

1. Register as an Etsy developer: https://www.etsy.com/developers/
2. Create a new application
3. Generate OAuth credentials
4. Configure the redirect URI to match your application URL + `/callback/etsy`

## Deployment

### Deploying to Render

1. Push your code to GitHub
2. Create a new Web Service in Render
3. Connect your GitHub repository
4. Configure the environment variables
5. Deploy!

## Project Structure

- `main.py` - Main application file
- `templates/` - HTML templates
- `static/` - Static assets (CSS, JavaScript, images)
- `static/uploads/` - Product images
- `catalog.json` - Product catalog storage

## License

This project is licensed under the MIT License - see the LICENSE file for details.
