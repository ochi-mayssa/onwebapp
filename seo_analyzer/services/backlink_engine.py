import os
import requests
import time
import base64
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Literal
from urllib.parse import urlparse
from django.conf import settings

# -------------------------------------------------------------------------
# Data Structures
# -------------------------------------------------------------------------

@dataclass
class BacklinkData:
    source_url: str
    target_url: str
    anchor_text: str
    is_dofollow: bool
    first_seen: str  # ISO date string
    referring_domain: str
    domain_authority: int
    spam_score: int
    classification: Literal['Healthy', 'Toxic', 'Neutral']
    http_status: Optional[int] = None
    verification_status: str = "Pending"

@dataclass
class AnalysisSummary:
    total_backlinks: int
    referring_domains_count: int
    dofollow_percentage: float
    toxic_links_count: int
    healthy_links_count: int
    avg_domain_authority: float

# -------------------------------------------------------------------------
# Service Implementation
# -------------------------------------------------------------------------

class BacklinkAnalyzer:
    """
    Real Backlink Analysis Engine using external APIs.
    Strictly prohibits fake data generation.
    """

    def __init__(self, api_provider: str = 'moz'):
        self.api_provider = api_provider.lower()
        
        # SECURITY: Load keys ONLY from environment variables
        if self.api_provider == 'moz':
            self.access_id = os.environ.get('MOZ_ACCESS_ID')
            self.secret_key = os.environ.get('MOZ_SECRET_KEY')
            
            if not self.access_id or not self.secret_key:
                raise ValueError(
                    "Backlink database not accessible – API keys required. "
                    "Please configure MOZ_ACCESS_ID and MOZ_SECRET_KEY in your environment."
                )

    def analyze_domain(self, domain: str) -> Dict:
        """
        Main entry point. Fetches real data, classifies it, and returns a structured report.
        """
        # 1. Fetch Raw Data from API (Strict)
        raw_links = self._fetch_links_from_api(domain)
        
        # 2. Process and Classify
        processed_links = []
        toxic_count = 0
        healthy_count = 0
        total_da = 0
        dofollow_count = 0
        unique_domains = set()

        for link in raw_links:
            # Classification Logic
            classification = self._classify_link(link)
            
            # Create Structured Object
            backlink = BacklinkData(
                source_url=link['source_url'],
                target_url=link['target_url'],
                anchor_text=link['anchor_text'],
                is_dofollow=link['is_dofollow'],
                first_seen=link['first_seen'],
                referring_domain=self._extract_domain(link['source_url']),
                domain_authority=link.get('domain_authority', 0),
                spam_score=link.get('spam_score', 0),
                classification=classification
            )
            
            # Update Stats
            processed_links.append(backlink)
            unique_domains.add(backlink.referring_domain)
            total_da += backlink.domain_authority
            
            if backlink.is_dofollow:
                dofollow_count += 1
            
            if classification == 'Toxic':
                toxic_count += 1
            elif classification == 'Healthy':
                healthy_count += 1

        # 3. Calculate Summary
        total_links = len(processed_links)
        summary = AnalysisSummary(
            total_backlinks=total_links,
            referring_domains_count=len(unique_domains),
            dofollow_percentage=round((dofollow_count / total_links * 100), 2) if total_links > 0 else 0,
            toxic_links_count=toxic_count,
            healthy_links_count=healthy_count,
            avg_domain_authority=round(total_da / total_links, 2) if total_links > 0 else 0
        )

        return {
            'domain': domain,
            'summary': asdict(summary),
            'backlinks': [asdict(l) for l in processed_links]
        }

    def verify_backlink_status(self, backlink_data: Dict) -> Dict:
        """
        Performs a REAL HTTP check (HEAD or GET) to verify if the backlink still exists.
        """
        url = backlink_data['source_url']
        try:
            # Use a realistic User-Agent to avoid immediate blocking
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
            }
            
            # Try HEAD first for efficiency
            try:
                response = requests.head(url, headers=headers, timeout=5, allow_redirects=True)
            except requests.RequestException:
                # Fallback to GET if HEAD is blocked/fails
                response = requests.get(url, headers=headers, timeout=10)

            backlink_data['http_status'] = response.status_code
            
            if response.status_code == 200:
                backlink_data['verification_status'] = "Active"
            elif response.status_code == 404 or response.status_code == 410:
                backlink_data['verification_status'] = "Dead (404/410)"
                # Re-classify as Toxic if dead
                backlink_data['classification'] = "Toxic" 
            elif 300 <= response.status_code < 400:
                backlink_data['verification_status'] = f"Redirect ({response.status_code})"
            else:
                backlink_data['verification_status'] = f"Status {response.status_code}"

        except requests.RequestException as e:
            backlink_data['http_status'] = 0
            backlink_data['verification_status'] = "Unreachable"
            # Potential toxicity if unreachable
            backlink_data['classification'] = "Toxic"
        
        return backlink_data

    # -------------------------------------------------------------------------
    # Internal Helpers & Logic
    # -------------------------------------------------------------------------

    def _fetch_links_from_api(self, domain: str) -> List[Dict]:
        """
        Connects to the Real API.
        """
        if self.api_provider == 'moz':
            return self._fetch_from_moz(domain)
        else:
            raise ValueError(f"Provider '{self.api_provider}' not implemented.")

    def _fetch_from_moz(self, domain: str) -> List[Dict]:
        """
        Real Moz API Integration.
        Reference: https://moz.com/help/links-api
        """
        # Generate Basic Auth
        token = base64.b64encode(f"{self.access_id}:{self.secret_key}".encode('utf-8')).decode('utf-8')
        headers = {'Authorization': f'Basic {token}'}
        
        # Endpoint: Moz Links API V2
        # Note: This is a simplified endpoint structure. Real implementation depends on exact Moz subscription.
        # Using a generic structure for 'links' to a target.
        endpoint = f"https://lsapi.seomoz.com/v2/links"
        
        params = {
            "target": domain,
            "target_scope": "domain",
            "filter": "external",
            "limit": 50, # Limit to avoid quota exhaustion
            "sort": "page_authority" 
        }

        try:
            print(f"Connecting to Moz API for {domain}...")
            response = requests.post(endpoint, json=params, headers=headers, timeout=15)
            
            if response.status_code == 401:
                raise ValueError("Moz API: Unauthorized. Check your Access ID and Secret Key.")
            
            if response.status_code != 200:
                raise ValueError(f"Moz API Error: {response.status_code} - {response.text}")
                
            data = response.json()
            
            # Parse Moz Response
            results = []
            for item in data.get('results', []):
                results.append({
                    'source_url': item.get('source', {}).get('page', ''),
                    'target_url': item.get('target', {}).get('page', ''),
                    'anchor_text': item.get('anchor_text', ''),
                    'is_dofollow': not item.get('is_nofollow', False),
                    'first_seen': item.get('first_seen', ''),
                    'domain_authority': item.get('source', {}).get('domain_authority', 0),
                    'spam_score': item.get('source', {}).get('spam_score', 0)
                })
            
            return results

        except requests.RequestException as e:
            # Network level error
            raise ValueError(f"Failed to connect to Backlink Database: {str(e)}")

    def _classify_link(self, link_data: Dict) -> str:
        """
        Classifies a link based on SEO metrics.
        """
        da = link_data.get('domain_authority', 0)
        spam = link_data.get('spam_score', 0)
        is_dofollow = link_data.get('is_dofollow', False)
        
        # 1. Toxic Rules
        if spam > 30:
            return 'Toxic'
        if da < 5 and spam > 10:
            return 'Toxic'
        
        # 2. Healthy Rules
        if da > 40 and spam < 5 and is_dofollow:
            return 'Healthy'
        if da > 20 and spam < 10 and is_dofollow:
            return 'Healthy'
            
        # 3. Default
        return 'Neutral'

    def _extract_domain(self, url: str) -> str:
        try:
            return urlparse(url).netloc
        except:
            return url
