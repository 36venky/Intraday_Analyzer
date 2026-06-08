import yfinance as yf
import re

# -----------------------------
# 1. Fetch company name
# -----------------------------
def get_company_name(symbol: str) -> str:
    """Fetch company name from Yahoo Finance."""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        company_name = info.get("longName") or info.get("shortName")
        if not company_name:
            return f"❌ Company name not found for {symbol}"
        return company_name
    except Exception as e:
        return f"⚠️ Error fetching company name for {symbol}: {e}"

# -----------------------------
# 2. Clean and normalize company name
# -----------------------------
def clean_company_name(name: str) -> str:
    """Clean company name for URL formatting."""
    name = name.strip()

    # Remove leading "The"
    if name.lower().startswith("the "):
        name = name[4:]

    # Replace multiple spaces
    name = re.sub(r'\s+', ' ', name)

    # Standardize common suffixes
    name = name.replace("Limited", "Ltd").replace("limited", "Ltd")
    name = name.replace("Private", "").replace("Pvt", "").strip()

    return name


# -----------------------------
# 3. Generate Groww URL slug
# -----------------------------
def get_groww_stock_link(company_name: str) -> str:
    """Generate Groww stock URL slug from company name."""
    base_url = "https://groww.in/stocks/"
    clean_name = clean_company_name(company_name)
    # Convert cleaned name to lowercase slug
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', clean_name.lower()).strip('-')
    return f"{base_url}{slug}"


# -----------------------------
# 4. Main wrapper function
# -----------------------------
def get_groww_link_from_symbol(symbol: str) -> str:
    """Get Groww stock URL from stock symbol."""
    company_name = get_company_name(symbol)
    if company_name.startswith("❌") or company_name.startswith("⚠️"):
        return company_name
    return get_groww_stock_link(company_name)

