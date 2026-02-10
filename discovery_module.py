"""
InsightIQ Discovery Module

Handles Instagram profile discovery via InsightIQ API with fixed base parameters.
"""

import base64
import requests
import time
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class InsightIQDiscovery:
    """
    InsightIQ discovery client with fixed parameters
    
    Fixed parameters (not user-configurable):
    - Email required (MUST_HAVE)
    - English creators only
    - USA creators only
    - USA audience 30%+
    - Sort by follower count descending
    - Audience credibility: EXCELLENT, HIGH, NORMAL
    """
    
    # Fixed parameters applied to ALL searches
    FIXED_PARAMS = {
        'specific_contact_details': [
            {'type': 'EMAIL', 'preference': 'MUST_HAVE'}
        ],
        'creator_language': {'code': 'en'},
        'creator_locations': ['cb8c4bd2-7661-4761-971a-c27322e2f209'],  # USA
        'audience_locations': [
            {
                'location_id': 'cb8c4bd2-7661-4761-971a-c27322e2f209',
                'percentage_value': 30,
                'operator': 'GT'
            }
        ],
        'sort_by': {
            'field': 'FOLLOWER_COUNT',
            'order': 'DESCENDING'
        },
        'audience_credibility_category': ['EXCELLENT', 'HIGH', 'NORMAL']
    }
    
    PLATFORM_CONFIGS = {
        'instagram': {
            'work_platform_id': '9bb8913b-ddd9-430b-a66a-d74d846e6c66',
            'network_name': 'instagram',
        },
        'youtube': {
            'work_platform_id': '14d9ddf5-51c6-415e-bde6-f8ed36ad7054',
            'network_name': 'youtube',
        },
        'tiktok': {
            'work_platform_id': 'de55aeec-0dc8-4119-bf90-16b3d1f0c987',
            'network_name': 'tiktok',
        },
        'facebook': {
            'work_platform_id': 'ad2fec62-2987-40a0-89fb-23485972598c',
            'network_name': 'facebook',
        }
    }
    
    def __init__(self, client_id, secret):
        """Initialize with InsightIQ credentials"""
        self.client_id = client_id
        self.secret = secret
        
        encoded = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
        self.headers = {'Authorization': f'Basic {encoded}'}
        
    def search_profiles(self, platform='instagram', user_filters=None):
        """
        Search for creator profiles with fixed base parameters
        
        Args:
            platform: 'instagram', 'youtube', 'tiktok', or 'facebook'
            user_filters: dict with ONLY user-configurable parameters:
                - max_results: int (1-4000)
                - follower_count: dict with min/max
                - lookalike_type: 'creator' or 'audience' (mutually exclusive)
                - lookalike_username: str (required if lookalike_type set)
                - creator_interests: list of str
                - hashtags: list of dicts [{"name": "travel"}, ...]
        
        Returns:
            List of profile dicts with standardized fields
        """
        if platform not in self.PLATFORM_CONFIGS:
            raise ValueError(f"Unsupported platform: {platform}")
        
        platform_config = self.PLATFORM_CONFIGS[platform]
        user_filters = user_filters or {}
        
        # Start with fixed parameters
        parameters = self.FIXED_PARAMS.copy()
        
        # Add platform
        parameters['work_platform_id'] = platform_config['work_platform_id']
        
        # Add max_results
        parameters['max_results'] = min(user_filters.get('max_results', 500), 4000)
        
        # Add follower count filter
        follower_filter = user_filters.get('follower_count', {})
        if platform == 'youtube':
            # YouTube uses subscriber_count
            parameters['subscriber_count'] = {
                'min': follower_filter.get('min', 20000),
                'max': follower_filter.get('max', 900000)
            }
        else:
            parameters['follower_count'] = {
                'min': follower_filter.get('min', 20000),
                'max': follower_filter.get('max', 900000)
            }
        
        # Add lookalike (mutually exclusive - enforce this!)
        lookalike_type = user_filters.get('lookalike_type')
        lookalike_username = user_filters.get('lookalike_username', '').strip()
        
        if lookalike_type == 'creator' and lookalike_username:
            parameters['creator_lookalikes'] = lookalike_username
            logger.info(f"Using creator lookalike: {lookalike_username}")
        elif lookalike_type == 'audience' and lookalike_username:
            parameters['audience_lookalikes'] = lookalike_username
            logger.info(f"Using audience lookalike: {lookalike_username}")
        
        # Add optional filters
        if 'creator_interests' in user_filters and user_filters['creator_interests']:
            parameters['creator_interests'] = user_filters['creator_interests']
            logger.info(f"Creator interests: {parameters['creator_interests']}")
        
        if 'hashtags' in user_filters and user_filters['hashtags']:
            parameters['hashtags'] = user_filters['hashtags']
            logger.info(f"Hashtags: {parameters['hashtags']}")
        
        # Start export job
        logger.info(f"Starting {platform} discovery with fixed parameters...")
        logger.info(f"Follower range: {parameters.get('follower_count', parameters.get('subscriber_count'))}")
        logger.info(f"Max results: {parameters['max_results']}")
        
        job_id = self._start_job(parameters)
        
        # Wait for results
        logger.info(f"Waiting for results (job_id: {job_id})...")
        raw_results = self._fetch_results(job_id)
        
        # Standardize output
        logger.info(f"Processing {len(raw_results)} profiles...")
        return self._standardize_results(raw_results, platform)
    
    def _start_job(self, parameters):
        """Start InsightIQ export job"""
        url = 'https://api.insightiq.ai/v1/social/creators/profiles/search-export'
        
        logger.info(f"API parameters: {parameters}")
        
        try:
            response = requests.post(url=url, headers=self.headers, json=parameters, timeout=30)
            
            if response.status_code != 200:
                logger.error(f"API error: {response.status_code} - {response.text}")
                raise Exception(f"Failed to start job: {response.text}")
            
            job_id = response.json().get('id')
            if not job_id:
                raise Exception("No job ID returned from API")
            
            logger.info(f"Job started successfully: {job_id}")
            return job_id
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            raise Exception(f"Failed to connect to InsightIQ API: {e}")
    
    def _fetch_results(self, job_id):
        """Poll for job results"""
        url = f'https://api.insightiq.ai/v1/social/creators/profiles/search-export/{job_id}'
        offset, limit = 0, 100
        all_results = []
        
        max_wait_time = 600  # 10 minutes max
        start_time = time.time()
        poll_count = 0
        
        while True:
            # Check timeout
            elapsed = time.time() - start_time
            if elapsed > max_wait_time:
                raise Exception(f"Job timeout after {max_wait_time} seconds")
            
            poll_count += 1
            
            try:
                response = requests.get(
                    url=url,
                    headers=self.headers,
                    params={'offset': offset, 'limit': limit},
                    timeout=30
                )
                
                if response.status_code != 200:
                    logger.error(f"Fetch error: {response.status_code} - {response.text}")
                    raise Exception(f"Failed to fetch results: {response.text}")
                
                data = response.json()
                
                # Check if job is still processing
                if data.get('status') == 'IN_PROGRESS':
                    logger.info(f"Job still processing (poll #{poll_count}, elapsed: {int(elapsed)}s), waiting 60 seconds...")
                    time.sleep(60)
                    continue
                
                # Check for errors
                if data.get('status') == 'FAILED':
                    error_msg = data.get('error', 'Unknown error')
                    raise Exception(f"Job failed: {error_msg}")
                
                # Job completed, collect results
                batch_results = data.get('data', [])
                all_results.extend(batch_results)
                
                total_results = data.get('metadata', {}).get('total_results', 0)
                
                logger.info(f"Fetched {len(all_results)}/{total_results} profiles")
                
                # Check if we've got all results
                if offset + limit >= total_results or len(batch_results) == 0:
                    break
                
                offset += limit
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed during fetch: {e}")
                raise Exception(f"Failed to fetch results: {e}")
        
        logger.info(f"Fetch complete: {len(all_results)} total profiles")
        return all_results
    
    def _standardize_results(self, raw_results, platform):
        """Convert raw API results to standardized format for HubSpot"""
        standardized = []
        
        for i, profile in enumerate(raw_results):
            try:
                # Extract contact details
                contact_details = self._extract_contact_details(
                    profile.get('contact_details', [])
                )
                
                # Parse name
                full_name = profile.get('full_name', '')
                name_parts = [n.capitalize() for n in full_name.split()] if full_name else []
                first_name = name_parts[0] if name_parts else ''
                last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
                
                # Get location
                location = profile.get('creator_location', {})
                
                # Standardized output
                standardized_profile = {
                    'profile_url': profile.get('url', ''),
                    'handle': profile.get('platform_username', ''),
                    'display_name': full_name,
                    'first_name': first_name,
                    'last_name': last_name,
                    'platform': platform,
                    'follower_count': profile.get('follower_count') or profile.get('subscriber_count', 0),
                    'engagement_rate': profile.get('engagement_rate', 0),
                    'bio': profile.get('bio', ''),
                    'email': contact_details.get('email'),
                    'phone': contact_details.get('phone'),
                    'city': location.get('city'),
                    'state': location.get('state'),
                    'country': location.get('country'),
                    'audience_credibility': profile.get('audience_credibility_category'),
                    'last_post_date': profile.get('last_post_timestamp'),
                    
                    # Additional contact URLs
                    **{k: v for k, v in contact_details.items() 
                       if k not in ('email', 'phone')}
                }
                
                standardized.append(standardized_profile)
                
            except Exception as e:
                logger.warning(f"Failed to process profile #{i+1}: {e}")
                continue
        
        logger.info(f"Successfully processed {len(standardized)} profiles")
        return standardized
    
    def _extract_contact_details(self, contact_details):
        """Extract and format contact details"""
        contacts = {}
        
        for detail in contact_details:
            contact_type = detail.get('type', '').lower()
            contact_value = detail.get('value', '')
            
            if contact_type and contact_value:
                if contact_type in ('email', 'phone'):
                    contacts[contact_type] = contact_value
                else:
                    # Other contact types (twitter, linkedin, etc.)
                    contacts[f'{contact_type}_url'] = contact_value
        
        return contacts


# Convenience function for quick testing
def test_discovery(client_id, secret, max_results=10):
    """
    Quick test function
    
    Usage:
        from discovery_module import test_discovery
        profiles = test_discovery('client_id', 'secret', max_results=10)
    """
    client = InsightIQDiscovery(client_id, secret)
    
    test_filters = {
        'max_results': max_results,
        'follower_count': {'min': 50000, 'max': 200000}
    }
    
    profiles = client.search_profiles(platform='instagram', user_filters=test_filters)
    
    print(f"\n✅ Found {len(profiles)} profiles")
    if profiles:
        print(f"\nSample profile:")
        sample = profiles[0]
        for key, value in sample.items():
            print(f"  {key}: {value}")
    
    return profiles


if __name__ == '__main__':
    # Test mode
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python discovery_module.py <client_id> <secret> [max_results]")
        sys.exit(1)
    
    client_id = sys.argv[1]
    secret = sys.argv[2]
    max_results = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    
    test_discovery(client_id, secret, max_results)
