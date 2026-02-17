"""
Seed URL discovery service for insurance policy crawling.

v7: Updated URLs to target specific policy document/wording pages.
    Added custom insurer persistence via JSON file.
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

import requests

from app.config import USER_AGENT

logger = logging.getLogger(__name__)

CUSTOM_INSURERS_FILE = Path(__file__).parent.parent.parent / "storage" / "custom_insurers.json"

NZ_INSURERS: Dict[str, Dict] = {
    "AA Insurance": {
        "seed_urls": [
            "https://www.aainsurance.co.nz/car-insurance/policy-documents",
            "https://www.aainsurance.co.nz/home-insurance/policy-documents",
            "https://www.aainsurance.co.nz/contents-insurance/policy-documents",
            "https://www.aainsurance.co.nz/landlord-insurance/policy-documents",
            "https://www.aainsurance.co.nz/travel-insurance/policy-documents",
            "https://www.aainsurance.co.nz/life-insurance/policy-documents",
            "https://www.aainsurance.co.nz/car-insurance",
            "https://www.aainsurance.co.nz/home-insurance",
        ],
        "policy_types": ["Motor", "Home", "Contents", "Landlord", "Travel", "Life"],
    },
    "AMI Insurance": {
        "seed_urls": [
            "https://www.ami.co.nz/insurance/car",
            "https://www.ami.co.nz/insurance/house",
            "https://www.ami.co.nz/insurance/contents",
            "https://www.ami.co.nz/insurance/landlord",
            "https://www.ami.co.nz/insurance/travel",
            "https://www.ami.co.nz/insurance/life",
            "https://www.ami.co.nz/car-insurance/policy-documents",
            "https://www.ami.co.nz/policy-documents",
        ],
        "policy_types": ["Motor", "Home", "Contents", "Landlord", "Travel", "Life"],
    },
    "Tower Insurance": {
        "seed_urls": [
            "https://www.tower.co.nz/insurance/car/policy-documents",
            "https://www.tower.co.nz/insurance/house/policy-documents",
            "https://www.tower.co.nz/insurance/car",
            "https://www.tower.co.nz/insurance/house",
            "https://www.tower.co.nz/insurance/contents",
            "https://www.tower.co.nz/insurance/landlord",
            "https://www.tower.co.nz/insurance/travel",
            "https://www.tower.co.nz/policy-documents",
            "https://www.tower.co.nz/pet-insurance",
            "https://www.tower.co.nz/life-insurance",
        ],
        "policy_types": ["Motor", "Home", "Contents", "Landlord", "Travel", "Pet", "Life"],
    },
    "State Insurance": {
        "seed_urls": [
            "https://www.state.co.nz/car-insurance/policy-documents",
            "https://www.state.co.nz/house-insurance/policy-documents",
            "https://www.state.co.nz/car-insurance",
            "https://www.state.co.nz/house-insurance",
            "https://www.state.co.nz/contents-insurance",
            "https://www.state.co.nz/travel-insurance",
            "https://www.state.co.nz/life-insurance",
            "https://www.state.co.nz/policy-documents",
        ],
        "policy_types": ["Motor", "Home", "Contents", "Travel", "Life"],
    },
    "Vero Insurance": {
        "seed_urls": [
            "https://www.vero.co.nz/policy-wordings.html",
            "https://www.vero.co.nz/personal/car-insurance.html",
            "https://www.vero.co.nz/personal/home-insurance.html",
            "https://www.vero.co.nz/personal.html",
            "https://www.vero.co.nz/business.html",
        ],
        "policy_types": ["Motor", "Home", "Contents", "Business"],
    },
    "AIA New Zealand": {
        "seed_urls": [
            "https://www.aia.co.nz/en/our-products.html",
            "https://www.aia.co.nz/en/individual/life-insurance.html",
            "https://www.aia.co.nz/en/individual/health-insurance.html",
            "https://www.aia.co.nz/en/help-support/policy-documents.html",
        ],
        "policy_types": ["Life", "Health"],
    },
    "Southern Cross": {
        "seed_urls": [
            "https://www.southerncross.co.nz/society/policy-documents",
            "https://www.southerncross.co.nz/insurance/health-insurance",
            "https://www.southerncross.co.nz/insurance/life-insurance",
            "https://www.southerncross.co.nz/insurance/travel-insurance",
            "https://www.southerncross.co.nz/insurance/pet-insurance",
            "https://www.southerncross.co.nz/insurance",
        ],
        "policy_types": ["Health", "Life", "Travel", "Pet"],
    },
    "Partners Life": {
        "seed_urls": [
            "https://www.partnerslife.co.nz/policy-documents",
            "https://www.partnerslife.co.nz/insurance",
            "https://www.partnerslife.co.nz/life-insurance",
        ],
        "policy_types": ["Life", "Health"],
    },
    "nib Insurance": {
        "seed_urls": [
            "https://www.nib.co.nz/policy-documents",
            "https://www.nib.co.nz/health-insurance",
        ],
        "policy_types": ["Health"],
    },
    "Fidelity Life": {
        "seed_urls": [
            "https://www.fidelitylife.co.nz/policy-documents",
            "https://www.fidelitylife.co.nz/insurance",
        ],
        "policy_types": ["Life", "Health"],
    },
    "Chubb Insurance NZ": {
        "seed_urls": [
            "https://www.chubb.com/nz-en/individuals-families/home-insurance.html",
            "https://www.chubb.com/nz-en/individuals-families.html",
            "https://www.chubb.com/nz-en/footer/policy-documents.html",
        ],
        "policy_types": ["Home", "Contents", "Travel", "Business"],
    },
    "Ando Insurance": {
        "seed_urls": [
            "https://www.ando.co.nz/car-insurance",
            "https://www.ando.co.nz/home-insurance",
            "https://www.ando.co.nz/policy-documents",
        ],
        "policy_types": ["Motor", "Home", "Contents"],
    },
    "Youi Insurance NZ": {
        "seed_urls": [
            "https://www.youi.co.nz/car-insurance",
            "https://www.youi.co.nz/home-insurance",
            "https://www.youi.co.nz/policy-documents",
        ],
        "policy_types": ["Motor", "Home", "Contents"],
    },
    "Trade Me Insurance": {
        "seed_urls": [
            "https://www.trademeinsurance.co.nz/car-insurance",
            "https://www.trademeinsurance.co.nz/policy-documents",
        ],
        "policy_types": ["Motor", "Home", "Contents"],
    },
    "Pinnacle Life": {
        "seed_urls": [
            "https://www.pinnaclelife.co.nz/life-insurance",
            "https://www.pinnaclelife.co.nz/policy-documents",
        ],
        "policy_types": ["Life"],
    },
    "Accuro Health Insurance": {
        "seed_urls": [
            "https://www.accuro.co.nz/plans",
            "https://www.accuro.co.nz",
        ],
        "policy_types": ["Health"],
    },
    "Cigna NZ": {
        "seed_urls": [
            "https://www.cignanz.co.nz/life-insurance",
            "https://www.cignanz.co.nz",
        ],
        "policy_types": ["Life", "Health"],
    },
    "MAS NZ": {
        "seed_urls": [
            "https://www.mas.co.nz/insurance/car-insurance",
            "https://www.mas.co.nz/insurance/home-insurance",
            "https://www.mas.co.nz/insurance",
        ],
        "policy_types": ["Motor", "Home", "Contents", "Life"],
    },
    "FMG Insurance": {
        "seed_urls": [
            "https://www.fmg.co.nz/insurance",
            "https://www.fmg.co.nz",
        ],
        "policy_types": ["Home", "Motor", "Business", "Contents"],
    },
    "NZI Insurance": {
        "seed_urls": [
            "https://www.nzi.co.nz/policy-wordings",
            "https://www.nzi.co.nz",
        ],
        "policy_types": ["Business", "Motor", "Home"],
    },
}

AU_INSURERS: Dict[str, Dict] = {
    "Allianz Australia": {
        "seed_urls": [
            "https://www.allianz.com.au/policy-documents",
            "https://www.allianz.com.au/car-insurance",
            "https://www.allianz.com.au/home-insurance",
            "https://www.allianz.com.au/travel-insurance",
            "https://www.allianz.com.au/business-insurance",
        ],
        "policy_types": ["Motor", "Home", "Contents", "Travel", "Business"],
    },
    "NRMA Insurance": {
        "seed_urls": [
            "https://www.nrma.com.au/policy-booklets",
            "https://www.nrma.com.au/car-insurance",
            "https://www.nrma.com.au/home-insurance",
            "https://www.nrma.com.au/travel-insurance",
        ],
        "policy_types": ["Motor", "Home", "Contents", "Travel"],
    },
    "QBE Insurance AU": {
        "seed_urls": [
            "https://www.qbe.com/au/policy-documents",
            "https://www.qbe.com/au/car-insurance",
            "https://www.qbe.com/au/home-insurance",
        ],
        "policy_types": ["Motor", "Home", "Business"],
    },
    "Suncorp Insurance": {
        "seed_urls": [
            "https://www.suncorp.com.au/insurance/policy-documents.html",
            "https://www.suncorp.com.au/insurance/car.html",
            "https://www.suncorp.com.au/insurance/home.html",
        ],
        "policy_types": ["Motor", "Home", "Contents", "Travel"],
    },
    "AAMI Insurance": {
        "seed_urls": [
            "https://www.aami.com.au/policy-documents.html",
            "https://www.aami.com.au/car-insurance.html",
            "https://www.aami.com.au/home-insurance.html",
        ],
        "policy_types": ["Motor", "Home", "Contents"],
    },
    "GIO Insurance": {
        "seed_urls": [
            "https://www.gio.com.au/policy-documents.html",
            "https://www.gio.com.au/car-insurance.html",
            "https://www.gio.com.au/home-insurance.html",
        ],
        "policy_types": ["Motor", "Home", "Travel", "Business"],
    },
    "Budget Direct": {
        "seed_urls": [
            "https://www.budgetdirect.com.au/car-insurance.html",
            "https://www.budgetdirect.com.au/home-insurance.html",
        ],
        "policy_types": ["Motor", "Home", "Contents", "Travel"],
    },
    "Youi Insurance AU": {
        "seed_urls": [
            "https://www.youi.com.au/car-insurance",
            "https://www.youi.com.au/home-insurance",
        ],
        "policy_types": ["Motor", "Home", "Contents"],
    },
    "Bupa Australia": {
        "seed_urls": [
            "https://www.bupa.com.au/health-insurance",
        ],
        "policy_types": ["Health"],
    },
    "AIA Australia": {
        "seed_urls": [
            "https://www.aia.com.au/en/individual/products.html",
            "https://www.aia.com.au/en/individual/products/life-insurance.html",
        ],
        "policy_types": ["Life", "Health"],
    },
}

UK_INSURERS: Dict[str, Dict] = {
    "Aviva": {
        "seed_urls": [
            "https://www.aviva.co.uk/insurance/motor",
            "https://www.aviva.co.uk/insurance/home",
            "https://www.aviva.co.uk/insurance/travel",
            "https://www.aviva.co.uk/insurance/life",
            "https://www.aviva.co.uk/business",
        ],
        "policy_types": ["Motor", "Home", "Travel", "Life", "Business"],
    },
    "Admiral Insurance": {
        "seed_urls": [
            "https://www.admiral.com/car-insurance",
            "https://www.admiral.com/home-insurance",
            "https://www.admiral.com/travel-insurance",
        ],
        "policy_types": ["Motor", "Home", "Travel", "Pet"],
    },
    "Direct Line": {
        "seed_urls": [
            "https://www.directline.com/car-insurance",
            "https://www.directline.com/home-insurance",
            "https://www.directline.com/travel-insurance",
            "https://www.directline.com/pet-insurance",
        ],
        "policy_types": ["Motor", "Home", "Travel", "Pet", "Life"],
    },
    "AXA UK": {
        "seed_urls": [
            "https://www.axa.co.uk/insurance/car-insurance",
            "https://www.axa.co.uk/insurance/home-insurance",
            "https://www.axa.co.uk/insurance/travel-insurance",
        ],
        "policy_types": ["Motor", "Home", "Travel", "Health"],
    },
    "Churchill": {
        "seed_urls": [
            "https://www.churchill.com/car-insurance",
            "https://www.churchill.com/home-insurance",
            "https://www.churchill.com/travel-insurance",
        ],
        "policy_types": ["Motor", "Home", "Travel", "Pet"],
    },
    "LV= Insurance": {
        "seed_urls": [
            "https://www.lv.com/car-insurance",
            "https://www.lv.com/home-insurance",
            "https://www.lv.com/travel-insurance",
            "https://www.lv.com/life-insurance",
        ],
        "policy_types": ["Motor", "Home", "Travel", "Life", "Pet"],
    },
    "Legal & General": {
        "seed_urls": [
            "https://www.legalandgeneral.com/insurance/life-insurance",
            "https://www.legalandgeneral.com/insurance/home-insurance",
            "https://www.legalandgeneral.com/insurance",
        ],
        "policy_types": ["Life", "Home"],
    },
    "Hastings Direct": {
        "seed_urls": [
            "https://www.hastingsdirect.com/car-insurance",
            "https://www.hastingsdirect.com/home-insurance",
        ],
        "policy_types": ["Motor", "Home"],
    },
    "Hiscox UK": {
        "seed_urls": [
            "https://www.hiscox.co.uk/business-insurance",
            "https://www.hiscox.co.uk/home-insurance",
        ],
        "policy_types": ["Business", "Home"],
    },
    "Saga Insurance": {
        "seed_urls": [
            "https://www.saga.co.uk/insurance/car-insurance",
            "https://www.saga.co.uk/insurance/home-insurance",
            "https://www.saga.co.uk/insurance/travel-insurance",
        ],
        "policy_types": ["Motor", "Home", "Travel", "Health"],
    },
    "Bupa UK": {
        "seed_urls": [
            "https://www.bupa.co.uk/health-insurance",
            "https://www.bupa.co.uk/travel-insurance",
        ],
        "policy_types": ["Health", "Travel"],
    },
}

COUNTRY_MAP = {
    "NZ": NZ_INSURERS,
    "AU": AU_INSURERS,
    "UK": UK_INSURERS,
}

COUNTRY_NAMES = {
    "NZ": "New Zealand",
    "AU": "Australia",
    "UK": "United Kingdom",
}


# ============================================================================
# CUSTOM INSURER PERSISTENCE
# ============================================================================

def _load_custom_insurers() -> Dict[str, Dict[str, Dict]]:
    if not CUSTOM_INSURERS_FILE.exists():
        return {}
    try:
        with open(CUSTOM_INSURERS_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load custom insurers: {e}")
        return {}


def _save_custom_insurers(data: Dict[str, Dict[str, Dict]]) -> None:
    CUSTOM_INSURERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CUSTOM_INSURERS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def add_custom_insurer(country: str, insurer_name: str, seed_urls: List[str], policy_types: Optional[List[str]] = None) -> Dict:
    custom = _load_custom_insurers()
    ck = country.upper()
    if ck not in custom:
        custom[ck] = {}
    custom[ck][insurer_name] = {"seed_urls": seed_urls, "policy_types": policy_types or []}
    _save_custom_insurers(custom)
    logger.info(f"Added custom insurer: {insurer_name} ({ck}) with {len(seed_urls)} URLs")
    return custom[ck][insurer_name]


def remove_custom_insurer(country: str, insurer_name: str) -> bool:
    custom = _load_custom_insurers()
    ck = country.upper()
    if ck in custom and insurer_name in custom[ck]:
        del custom[ck][insurer_name]
        _save_custom_insurers(custom)
        return True
    return False


def list_custom_insurers(country: Optional[str] = None) -> Dict:
    custom = _load_custom_insurers()
    if country:
        return {country.upper(): custom.get(country.upper(), {})}
    return custom


def resolve_insurers_from_urls(seed_urls: List[str], country: str = "NZ") -> List[str]:
    all_insurers = get_seed_urls(country=country)
    matched = set()
    for entry in all_insurers:
        for url in entry["seed_urls"]:
            if url in seed_urls:
                matched.add(entry["insurer"])
                break
    return sorted(matched)


# ============================================================================
# SERVICE FUNCTIONS
# ============================================================================

def get_seed_urls(country: str = "NZ", policy_type: Optional[str] = None, insurer: Optional[str] = None, validate: bool = False) -> List[Dict]:
    ck = country.upper()
    insurer_db = dict(COUNTRY_MAP.get(ck, {}))
    custom = _load_custom_insurers()
    if ck in custom:
        for name, info in custom[ck].items():
            insurer_db[name] = info

    if not insurer_db:
        logger.warning(f"No insurers configured for country: {country}")
        return []

    results = []
    for name, info in insurer_db.items():
        if insurer and insurer.lower() not in name.lower():
            continue
        if policy_type and policy_type not in info.get("policy_types", []):
            continue
        is_custom = ck in custom and name in custom.get(ck, {})
        entry = {"insurer": name, "seed_urls": info["seed_urls"], "policy_types": info.get("policy_types", []), "country": ck, "is_custom": is_custom}
        if validate:
            entry["validated_urls"] = _validate_urls(info["seed_urls"])
        results.append(entry)

    logger.info(f"Seed URL lookup: country={country}, policy_type={policy_type}, insurer={insurer} -> {len(results)} insurers found")
    return results


def get_all_seed_urls_flat(country: str = "NZ", policy_type: Optional[str] = None) -> List[str]:
    results = get_seed_urls(country=country, policy_type=policy_type)
    urls = []
    for entry in results:
        urls.extend(entry["seed_urls"])
    return urls


def get_supported_countries() -> List[str]:
    return list(COUNTRY_MAP.keys())


def get_insurers_list(country: str = "NZ") -> List[str]:
    insurer_db = dict(COUNTRY_MAP.get(country.upper(), {}))
    custom = _load_custom_insurers()
    if country.upper() in custom:
        insurer_db.update(custom[country.upper()])
    return list(insurer_db.keys())


def _validate_urls(urls: List[str]) -> List[Dict]:
    validated = []
    headers = {"User-Agent": USER_AGENT}
    for url in urls:
        try:
            resp = requests.head(url, timeout=10, headers=headers, allow_redirects=True, verify=False)
            validated.append({"url": url, "reachable": resp.status_code < 400, "status_code": resp.status_code})
        except Exception as e:
            validated.append({"url": url, "reachable": False, "status_code": None, "error": str(e)})
    return validated


__all__ = [
    'get_seed_urls', 'get_all_seed_urls_flat', 'get_supported_countries',
    'get_insurers_list', 'add_custom_insurer', 'remove_custom_insurer',
    'list_custom_insurers', 'resolve_insurers_from_urls',
]
