"""
Discovery Tasks - Add to your existing tasks.py

These tasks integrate with your existing Celery setup.
"""

import os
import logging
import json
import time
from datetime import datetime
import requests

# Import your existing Celery app
# from your_tasks import celery_app, r

# Import the discovery module
from discovery_module import InsightIQDiscovery

logger = logging.getLogger(__name__)


@celery_app.task(name='tasks.discover_instagram_profiles')
def discover_instagram_profiles(user_filters=None, job_id=None):
    """
    Run Instagram profile discovery with fixed base parameters
    
    Args:
        user_filters: dict with ONLY user-configurable parameters:
            - max_results: int (1-4000)
            - follower_count: {min: int, max: int}
            - lookalike_type: 'creator' or 'audience' (mutually exclusive!)
            - lookalike_username: str
            - creator_interests: list of str
            - hashtags: list of dicts [{"name": "travel"}, ...]
        job_id: optional job tracking ID
    
    Returns:
        dict with results summary
    """
    if job_id is None:
        job_id = discover_instagram_profiles.request.id
    
    try:
        # Update status
        update_discovery_job_status(job_id, status='discovering')
        
        # Get credentials from environment
        client_id = os.getenv('INSIGHTIQ_CLIENT_ID')
        secret = os.getenv('INSIGHTIQ_SECRET')
        
        if not client_id or not secret:
            raise ValueError("INSIGHTIQ_CLIENT_ID and INSIGHTIQ_SECRET must be set in environment")
        
        # Validate lookalikes are mutually exclusive
        user_filters = user_filters or {}
        lookalike_type = user_filters.get('lookalike_type')
        lookalike_username = user_filters.get('lookalike_username', '').strip()
        
        if lookalike_type and lookalike_type not in ('creator', 'audience'):
            raise ValueError("lookalike_type must be 'creator' or 'audience'")
        
        if lookalike_type and not lookalike_username:
            raise ValueError("lookalike_username required when lookalike_type is set")
        
        logger.info(f"Starting discovery with filters: {user_filters}")
        
        # Initialize client
        client = InsightIQDiscovery(client_id, secret)
        
        # Run discovery
        profiles = client.search_profiles(platform='instagram', user_filters=user_filters)
        
        logger.info(f"Discovery complete: {len(profiles)} profiles found")
        
        # Update status
        update_discovery_job_status(job_id, status='importing', profiles_found=len(profiles))
        
        # Import to HubSpot
        import_results = import_profiles_to_hubspot(profiles, job_id)
        
        # Final status
        update_discovery_job_status(
            job_id,
            status='completed',
            profiles_found=len(profiles),
            new_contacts_created=import_results['created'],
            duplicates_skipped=import_results['skipped']
        )
        
        logger.info(f"Job {job_id} completed: {import_results['created']} created, {import_results['skipped']} skipped")
        
        return {
            'status': 'completed',
            'profiles_found': len(profiles),
            'new_contacts': import_results['created'],
            'duplicates': import_results['skipped']
        }
        
    except Exception as e:
        logger.error(f"Discovery failed: {e}", exc_info=True)
        update_discovery_job_status(job_id, status='failed', error=str(e))
        raise


def update_discovery_job_status(job_id, status, **kwargs):
    """
    Update discovery job status in Redis
    
    Args:
        job_id: Job ID
        status: Job status (queued, discovering, importing, completed, failed)
        **kwargs: Additional fields to update (profiles_found, new_contacts_created, etc.)
    """
    job_key = f'discovery_job:{job_id}'
    
    # Get existing job data
    job_data = r.get(job_key)
    if job_data:
        job_data = json.loads(job_data)
    else:
        job_data = {'job_id': job_id}
    
    # Update fields
    job_data['status'] = status
    job_data['updated_at'] = datetime.now().isoformat()
    job_data.update(kwargs)
    
    # Save with 24 hour TTL
    r.setex(job_key, 86400, json.dumps(job_data))
    
    logger.info(f"Job {job_id} status updated: {status}")


def import_profiles_to_hubspot(profiles, job_id):
    """
    Import discovered profiles to HubSpot via batch API
    
    Args:
        profiles: List of profile dicts from InsightIQDiscovery
        job_id: Discovery job ID for tracking
    
    Returns:
        dict with {'created': int, 'skipped': int}
    """
    HUBSPOT_API_KEY = os.getenv('HUBSPOT_API_KEY')
    HUBSPOT_API_URL = 'https://api.hubapi.com'
    
    if not HUBSPOT_API_KEY:
        raise ValueError("HUBSPOT_API_KEY must be set in environment")
    
    contacts = []
    
    logger.info(f"Preparing {len(profiles)} profiles for HubSpot import")
    
    for profile in profiles:
        # Map discovery fields to HubSpot properties
        properties = {
            # Core identity
            'platform': profile.get('platform', 'instagram'),
            'profile_url': profile['profile_url'],
            'instagram_handle': profile.get('handle', ''),
            
            # Name
            'firstname': profile.get('first_name', ''),
            'lastname': profile.get('last_name', ''),
            
            # Metrics
            'followers': profile.get('follower_count', 0),
            'engagement_rate': profile.get('engagement_rate', 0),
            
            # Contact info
            'email': profile.get('email'),
            'phone': profile.get('phone'),
            
            # Location
            'city': profile.get('city'),
            'state': profile.get('state'),
            'country': profile.get('country'),
            
            # Bio/description (truncate for HubSpot limits)
            'bio': profile.get('bio', '')[:5000] if profile.get('bio') else '',
            
            # Discovery metadata
            'discovery_source': 'insightiq_discovery',
            'discovery_job_id': job_id,
            'discovery_date': datetime.now().isoformat(),
            'enrichment_status': 'pending',
            
            # Lead qualification
            'lifecycle_stage': 'lead',
            'audience_credibility': profile.get('audience_credibility'),
            'last_post_date': profile.get('last_post_date')
        }
        
        # Add any additional contact URLs (twitter, linkedin, etc.)
        for key, value in profile.items():
            if key.endswith('_url') and key not in ('profile_url',):
                properties[key] = value
        
        # Remove None values (HubSpot API doesn't like them)
        properties = {k: v for k, v in properties.items() if v is not None}
        
        contacts.append({'properties': properties})
    
    # Batch import (max 100 per request)
    created_count = 0
    skipped_count = 0
    total_batches = (len(contacts) + 99) // 100
    
    logger.info(f"Importing in {total_batches} batches...")
    
    for i in range(0, len(contacts), 100):
        batch = contacts[i:i+100]
        batch_num = (i // 100) + 1
        
        try:
            logger.info(f"Importing batch {batch_num}/{total_batches} ({len(batch)} contacts)...")
            
            response = requests.post(
                f"{HUBSPOT_API_URL}/crm/v3/objects/contacts/batch/create",
                headers={
                    'Authorization': f'Bearer {HUBSPOT_API_KEY}',
                    'Content-Type': 'application/json'
                },
                json={'inputs': batch},
                timeout=30
            )
            
            if response.status_code == 201:
                # All created successfully
                created_count += len(batch)
                logger.info(f"Batch {batch_num}: {len(batch)} contacts created")
                
            elif response.status_code == 207:
                # Multi-status: some created, some duplicates
                result = response.json()
                batch_created = len(result.get('results', []))
                batch_errors = result.get('errors', [])
                batch_skipped = len(batch_errors)
                
                created_count += batch_created
                skipped_count += batch_skipped
                
                logger.info(f"Batch {batch_num}: {batch_created} created, {batch_skipped} duplicates/errors")
                
                # Log first few errors for debugging
                for error in batch_errors[:3]:
                    logger.debug(f"Error: {error.get('message', 'Unknown error')}")
                
            else:
                # Error
                logger.error(f"Batch import error: {response.status_code} - {response.text}")
                skipped_count += len(batch)
        
        except Exception as e:
            logger.error(f"Exception importing batch {batch_num}: {e}")
            skipped_count += len(batch)
        
        # Small delay between batches to avoid rate limits
        if i + 100 < len(contacts):
            time.sleep(0.5)
    
    logger.info(f"Import complete: {created_count} created, {skipped_count} skipped/errors")
    
    return {
        'created': created_count,
        'skipped': skipped_count
    }


# Example of how to call this from your existing workflow
"""
# In your existing tasks.py, you can add:

from discovery_tasks import discover_instagram_profiles

# Then trigger discovery from anywhere:
task = discover_instagram_profiles.delay(
    user_filters={
        'max_results': 100,
        'follower_count': {'min': 50000, 'max': 500000},
        'lookalike_type': 'creator',
        'lookalike_username': '@shaunaglenndesign'
    }
)
"""
