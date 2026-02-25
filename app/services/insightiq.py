"""
InsightIQ API client — content fetching + discovery.
"""
import base64
import time
import requests
from typing import Dict, List, Any

from app.config import (
    INSIGHTIQ_USERNAME, INSIGHTIQ_PASSWORD,
    INSIGHTIQ_WORK_PLATFORM_ID, INSIGHTIQ_API_URL,
    INSIGHTIQ_CLIENT_ID, INSIGHTIQ_SECRET,
)


def fetch_social_content(profile_url: str) -> Dict[str, Any]:
    """Fetch content from InsightIQ API."""
    url = f"{INSIGHTIQ_API_URL}/v1/social/creators/contents/fetch"

    credentials = f"{INSIGHTIQ_USERNAME}:{INSIGHTIQ_PASSWORD}"
    encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')

    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "profile_url": profile_url,
        "work_platform_id": INSIGHTIQ_WORK_PLATFORM_ID,
    }

    print(f"InsightIQ Request URL: {url}")
    print(f"Profile URL: {profile_url}")
    print(f"Work Platform ID: {INSIGHTIQ_WORK_PLATFORM_ID}")

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        print(f"InsightIQ Response Status: {response.status_code}")
        if response.status_code != 200:
            print(f"ERROR Response Body: {response.text}")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"InsightIQ API Error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response Status: {e.response.status_code}")
            print(f"Response Body: {e.response.text}")
        raise


def filter_content_items(content_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter out Stories from content items."""
    filtered = [item for item in content_items if item.get('type') != 'STORY']
    print(f"Filtered content: {len(content_items)} total → {len(filtered)} after removing Stories")
    return filtered


# ──────────────────────────────────────────────────────────────────────────────
# InsightIQ Discovery Class
# ──────────────────────────────────────────────────────────────────────────────

class InsightIQDiscovery:
    """
    InsightIQ discovery client with fixed base parameters.

    Fixed:
    - Email required (MUST_HAVE)
    - English creators only
    - USA creators / audience 30%+
    - Audience credibility: EXCELLENT, HIGH, NORMAL
    """

    FIXED_PARAMS = {
        'specific_contact_details': [
            {'type': 'EMAIL', 'preference': 'MUST_HAVE'}
        ],
        'creator_language': {'code': 'en'},
        'creator_locations': ['cb8c4bd2-7661-4761-971a-c27322e2f209'],
        'audience_locations': [
            {
                'location_id': 'cb8c4bd2-7661-4761-971a-c27322e2f209',
                'percentage_value': 30,
                'operator': 'GT',
            }
        ],
        'sort_by': {'field': 'FOLLOWER_COUNT', 'order': 'DESCENDING'},
        'audience_credibility_category': ['EXCELLENT', 'HIGH', 'NORMAL'],
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
        },
    }

    def __init__(self, client_id=None, secret=None):
        self.client_id = client_id or INSIGHTIQ_CLIENT_ID
        self.secret = secret or INSIGHTIQ_SECRET
        encoded = base64.b64encode(f"{self.client_id}:{self.secret}".encode()).decode()
        self.headers = {'Authorization': f'Basic {encoded}'}

    def search_profiles(self, platform='instagram', user_filters=None):
        """Search for creator profiles with fixed base parameters."""
        if platform not in self.PLATFORM_CONFIGS:
            raise ValueError(f"Unsupported platform: {platform}")

        platform_config = self.PLATFORM_CONFIGS[platform]
        user_filters = user_filters or {}

        parameters = self.FIXED_PARAMS.copy()
        parameters['work_platform_id'] = platform_config['work_platform_id']
        parameters['max_results'] = min(user_filters.get('max_results', 500), 4000)

        # Follower count
        follower_filter = user_filters.get('follower_count', {})
        if platform == 'youtube':
            parameters['subscriber_count'] = {
                'min': follower_filter.get('min', 20000),
                'max': follower_filter.get('max', 900000),
            }
        else:
            parameters['follower_count'] = {
                'min': follower_filter.get('min', 20000),
                'max': follower_filter.get('max', 900000),
            }

        # Lookalike
        lookalike_type = user_filters.get('lookalike_type')
        lookalike_username = user_filters.get('lookalike_username', '').strip()
        if lookalike_type == 'creator' and lookalike_username:
            parameters['creator_lookalikes'] = lookalike_username
        elif lookalike_type == 'audience' and lookalike_username:
            parameters['audience_lookalikes'] = lookalike_username

        # Optional filters
        if user_filters.get('creator_interests'):
            parameters['creator_interests'] = user_filters['creator_interests']
        if user_filters.get('audience_interests'):
            parameters['audience_interests'] = user_filters['audience_interests']
        if user_filters.get('hashtags'):
            parameters['hashtags'] = user_filters['hashtags']

        # Bio phrase filtering
        bio_phrase = (user_filters.get('bio_phrase') or '').strip()
        bio_phrase_advanced = user_filters.get('bio_phrase_advanced') or []
        if bio_phrase_advanced and isinstance(bio_phrase_advanced, list):
            valid_actions = {'AND', 'OR', 'NOT'}
            cleaned = [
                {'bio_phrase': str(e['bio_phrase']).strip(), 'action': e['action']}
                for e in bio_phrase_advanced
                if isinstance(e, dict)
                and e.get('bio_phrase', '').strip()
                and e.get('action') in valid_actions
            ][:14]
            if cleaned:
                parameters['bio_phrase_advanced'] = cleaned
        elif bio_phrase:
            parameters['bio_phrase'] = bio_phrase

        print(f"Starting {platform} discovery with fixed parameters...")
        job_id = self._start_job(parameters)
        raw_results = self._fetch_results(job_id)
        return self._standardize_results(raw_results, platform)

    def _start_job(self, parameters):
        url = 'https://api.insightiq.ai/v1/social/creators/profiles/search-export'
        try:
            response = requests.post(url=url, headers=self.headers, json=parameters, timeout=30)
            if response.status_code not in (200, 202):
                raise Exception(f"Failed to start job: {response.text}")
            job_id = response.json().get('id')
            if not job_id:
                raise Exception("No job ID returned from API")
            print(f"Job started successfully: {job_id}")
            return job_id
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to connect to InsightIQ API: {e}")

    def _fetch_results(self, job_id):
        url = f'https://api.insightiq.ai/v1/social/creators/profiles/search-export/{job_id}'
        offset, limit = 0, 100
        all_results = []
        max_wait_time = 600
        start_time = time.time()
        poll_count = 0

        while True:
            elapsed = time.time() - start_time
            if elapsed > max_wait_time:
                raise Exception(f"Job timeout after {max_wait_time} seconds")
            poll_count += 1
            try:
                response = requests.get(
                    url=url, headers=self.headers,
                    params={'offset': offset, 'limit': limit}, timeout=30,
                )
                if response.status_code != 200:
                    raise Exception(f"Failed to fetch results: {response.text}")
                data = response.json()
                if data.get('status') == 'IN_PROGRESS':
                    print(f"Job still processing (poll #{poll_count}, elapsed: {int(elapsed)}s), waiting 60 seconds...")
                    time.sleep(60)
                    continue
                if data.get('status') == 'FAILED':
                    raise Exception(f"Job failed: {data.get('error', 'Unknown error')}")
                batch_results = data.get('data', [])
                all_results.extend(batch_results)
                total_results = data.get('metadata', {}).get('total_results', 0)
                print(f"Fetched {len(all_results)}/{total_results} profiles")
                if offset + limit >= total_results or len(batch_results) == 0:
                    break
                offset += limit
            except requests.exceptions.RequestException as e:
                raise Exception(f"Failed to fetch results: {e}")

        print(f"Fetch complete: {len(all_results)} total profiles")
        return all_results

    def _standardize_results(self, raw_results, platform):
        standardized = []
        for i, profile in enumerate(raw_results):
            try:
                contact_details = self._extract_contact_details(
                    profile.get('contact_details', [])
                )
                location = profile.get('location', {})
                standardized.append({
                    'first_and_last_name': profile.get('full_name', ''),
                    'flagship_social_platform_handle': profile.get('platform_username', ''),
                    'instagram_handle': profile.get('url', ''),
                    'instagram_bio': profile.get('introduction', ''),
                    'instagram_followers': profile.get('follower_count', 0),
                    'average_engagement': profile.get('engagement_rate', 0),
                    'email': contact_details.get('email'),
                    'phone': contact_details.get('phone'),
                    'tiktok_handle': contact_details.get('tiktok'),
                    'youtube_profile_link': contact_details.get('youtube'),
                    'facebook_profile_link': contact_details.get('facebook'),
                    'patreon_link': contact_details.get('patreon'),
                    'pinterest_profile_link': contact_details.get('pinterest'),
                    'city': location.get('city'),
                    'state': location.get('state'),
                    'country': location.get('country'),
                    'flagship_social_platform': 'instagram',
                    'channel': 'Outbound',
                    'channel_host_prospected': 'Phyllo',
                    'funnel': 'Creator',
                    'enrichment_status': 'pending',
                })
            except Exception as e:
                print(f"Failed to process profile #{i+1}: {e}")
        print(f"Successfully processed {len(standardized)} profiles")
        return standardized

    def _extract_contact_details(self, contact_details):
        contacts = {}
        for detail in contact_details:
            contact_type = detail.get('type', '').lower()
            contact_value = detail.get('value', '')
            if contact_type and contact_value and contact_type not in contacts:
                contacts[contact_type] = contact_value
        return contacts
