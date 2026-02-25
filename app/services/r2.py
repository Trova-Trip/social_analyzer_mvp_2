"""
Cloudflare R2 media operations — upload, rehost, cache.
"""
import io
import json
import hashlib
import requests
import concurrent.futures
from datetime import datetime
from typing import Dict, List
from PIL import Image

from app.config import R2_BUCKET_NAME, R2_PUBLIC_URL
from app.extensions import r2_client


def rehost_media_on_r2(media_url: str, contact_id: str, media_format: str) -> str:
    """Download media from Instagram CDN and upload to R2."""
    if not r2_client:
        return media_url

    try:
        max_retries = 2
        for attempt in range(max_retries):
            try:
                media_response = requests.get(media_url, timeout=15)
                media_response.raise_for_status()
                break
            except requests.exceptions.Timeout:
                if attempt == max_retries - 1:
                    print(f"Media download timed out after {max_retries} attempts, using original URL")
                    return media_url
                print(f"Download timeout, retrying... (attempt {attempt + 1}/{max_retries})")

        url_hash = hashlib.md5(media_url.encode()).hexdigest()
        extension = 'mp4' if media_format == 'VIDEO' else 'jpg'
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        object_key = f"social_content/{contact_id}/{timestamp}_{url_hash}.{extension}"
        content_type = 'video/mp4' if media_format == 'VIDEO' else 'image/jpeg'

        r2_client.put_object(
            Bucket=R2_BUCKET_NAME, Key=object_key,
            Body=media_response.content, ContentType=content_type,
        )

        rehosted_url = f"{R2_PUBLIC_URL}/{object_key}"
        print(f"Successfully re-hosted to R2: {object_key}")
        return rehosted_url

    except Exception as e:
        print(f"ERROR re-hosting media: {e}")
        return media_url


def create_thumbnail_grid(thumbnail_urls: List[str], contact_id: str) -> str:
    """Create a 3x4 grid image from up to 12 thumbnails and upload to R2."""
    def download_single_image(url):
        try:
            response = requests.get(url, timeout=10)
            img = Image.open(io.BytesIO(response.content))
            return img.resize((400, 400), Image.Resampling.LANCZOS)
        except Exception as e:
            print(f"Error loading thumbnail {url}: {e}")
            return Image.new('RGB', (400, 400), color='gray')

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        images = list(executor.map(download_single_image, thumbnail_urls[:12]))

    while len(images) < 12:
        images.append(Image.new('RGB', (400, 400), color='lightgray'))

    grid_width = 400 * 3
    grid_height = 400 * 4
    grid = Image.new('RGB', (grid_width, grid_height))

    for idx, img in enumerate(images[:12]):
        col = idx % 3
        row = idx // 3
        grid.paste(img, (col * 400, row * 400))

    buffer = io.BytesIO()
    grid.save(buffer, format='JPEG', quality=85)
    buffer.seek(0)

    key = f"thumbnail-grids/{contact_id}.jpg"
    r2_client.put_object(
        Bucket=R2_BUCKET_NAME, Key=key,
        Body=buffer.getvalue(), ContentType='image/jpeg',
    )

    grid_url = f"{R2_PUBLIC_URL}/{key}"
    print(f"Thumbnail grid created: {grid_url}")
    return grid_url


def save_analysis_cache(contact_id: str, cache_data: dict) -> bool:
    """Save analysis results to R2 for later re-scoring."""
    if not r2_client:
        print("R2 client not available, skipping cache")
        return False

    try:
        key = f"analysis-cache/{contact_id}.json"
        r2_client.put_object(
            Bucket=R2_BUCKET_NAME, Key=key,
            Body=json.dumps(cache_data, indent=2),
            ContentType='application/json',
        )
        print(f"Analysis cached to R2: {key}")
        return True
    except Exception as e:
        print(f"Error caching analysis: {e}")
        return False


def load_analysis_cache(contact_id: str) -> dict:
    """Load cached analysis results from R2."""
    if not r2_client:
        raise Exception("R2 client not available")

    try:
        key = f"analysis-cache/{contact_id}.json"
        obj = r2_client.get_object(Bucket=R2_BUCKET_NAME, Key=key)
        cache_data = json.loads(obj['Body'].read())
        print(f"Analysis loaded from cache: {key}")
        return cache_data
    except Exception as e:
        print(f"Error loading cache: {e}")
        raise
