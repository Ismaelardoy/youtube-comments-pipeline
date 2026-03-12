import azure.functions as func
import logging
import os
import json
import random
import html
import re
import emoji
from googleapiclient.discovery import build
from azure.storage.blob import BlobServiceClient
from datetime import datetime, timedelta

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

def clean_comment_text(text: str) -> str:
    if not text:
        return ""
    # Unescape HTML entities (e.g. &#39; to ')
    text = html.unescape(text)
    # Remove all HTML tags (like <br>, <a href...>)
    text = re.sub(r'<[^>]+>', ' ', text)
    # Remove raw URL strings completely
    text = re.sub(r'http[s]?://\S+', '', text)
    # Remove emojis
    text = emoji.replace_emoji(text, replace='')
    # Clean up excess whitespace created by removal
    text = re.sub(r'\s+', ' ', text).strip()
    return text

@app.route(route="extract_youtube_comments")
def extract_youtube_comments(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    youtube_api_key = os.environ.get("YOUTUBE_API_KEY")
    azure_conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    
    if not youtube_api_key or not azure_conn_str:
        return func.HttpResponse(
             "Missing environment variables 'YOUTUBE_API_KEY' or 'AZURE_STORAGE_CONNECTION_STRING'.",
             status_code=500
        )

    try:
        youtube = build('youtube', 'v3', developerKey=youtube_api_key)

        # Get parameters from query string or body
        video_id = req.params.get('video_id')
        theme = req.params.get('theme')
        is_short_str = req.params.get('is_short')
        upload_to_cloud_str = req.params.get('upload_to_cloud')
        
        try:
            req_body = req.get_json()
            if not video_id:
                video_id = req_body.get('video_id')
            if not theme:
                theme = req_body.get('theme')
            if is_short_str is None:
                # Need to convert boolean to string for comparison safely if provided
                is_short_val = req_body.get('is_short')
                if is_short_val is not None:
                    is_short_str = str(is_short_val)
            if upload_to_cloud_str is None:
                upload_to_cloud_val = req_body.get('upload_to_cloud')
                if upload_to_cloud_val is not None:
                    upload_to_cloud_str = str(upload_to_cloud_val)
        except ValueError:
            pass
            
        if is_short_str is None:
            is_short_str = 'false'
        if upload_to_cloud_str is None:
            upload_to_cloud_str = 'true'
            
        is_short = is_short_str.lower() == 'true'
        upload_to_cloud = upload_to_cloud_str.lower() == 'true'
        
        # Search Mode: If no video ID is provided, search using the theme
        if not video_id:
            if not theme:
                return func.HttpResponse(
                     "Please provide a 'video_id' or a 'theme' parameter.",
                     status_code=400
                )
            
            search_query = f"{theme} #shorts" if is_short else theme
            video_duration = "short" if is_short else "long"

            # Generate a random date from Jan 1, 2025 to today
            start_date = datetime(2025, 1, 1)
            end_date = datetime.utcnow()
            delta = end_date - start_date
            random_days = random.randrange(max(1, delta.days)) # Avoid error if executed same day
            random_published_after = (start_date + timedelta(days=random_days)).strftime('%Y-%m-%dT%H:%M:%SZ')
            
            logging.info(f"Search mode: Searching for '{search_query}' with min date {random_published_after} and duration '{video_duration}'...")

            search_request = youtube.search().list(
                part="snippet",
                q=search_query,
                type="video",
                videoDuration=video_duration,
                relevanceLanguage="en",
                publishedAfter=random_published_after,
                maxResults=50 # Request 50 and pick all available
            )
            search_response = search_request.execute()
            
            video_ids = []
            if 'items' in search_response and search_response['items']:
                video_ids = [item['id']['videoId'] for item in search_response['items']]
                logging.info(f"Obtained {len(video_ids)} videos from search.")
            else:
                return func.HttpResponse("No videos found for the given theme.", status_code=404)
        else:
            # If a video ID was provided directly in the query
            video_ids = [video_id]

        # 1. Extract comments iteratively
        comments_data = []
        GLOBAL_LIMIT = 10000
        
        for v_id in video_ids:
            if len(comments_data) >= GLOBAL_LIMIT:
                break
                
            logging.info(f"Extracting comments for video: {v_id}. Accumulated: {len(comments_data)}")
            
            try:
                request = youtube.commentThreads().list(
                    part="snippet",
                    videoId=v_id,
                    maxResults=100
                )
                
                while request is not None and len(comments_data) < GLOBAL_LIMIT:
                    response = request.execute()
                    
                    for item in response.get('items', []):
                        if len(comments_data) >= GLOBAL_LIMIT:
                            break
                        comment = item['snippet']['topLevelComment']['snippet']
                        
                        raw_text = comment.get('textDisplay', '')
                        cleaned_text = clean_comment_text(raw_text)
                        
                        if cleaned_text:
                            comments_data.append({
                                'videoId': v_id, # Add video ID to know data source
                                'theme': theme,  # Include theme inside each comment
                                'is_short': is_short, # Include is_short flag
                                'author': comment.get('authorDisplayName'),
                                'text': cleaned_text, # Cleaned comment text without HTML
                                'likeCount': comment.get('likeCount', 0), # Likes
                                'publishedAt': comment.get('publishedAt') # Published date
                            })
                    
                    # Pagination: if there are more comments and limit not reached
                    if 'nextPageToken' in response and len(comments_data) < GLOBAL_LIMIT:
                        request = youtube.commentThreads().list_next(
                            previous_request=request, 
                            previous_response=response
                        )
                    else:
                        break
            except Exception as e:
                logging.error(f"Error extracting comments from video {v_id}. Skipping to next. Error: {str(e)}")
                continue

        # 2. Save massive data
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        
        if len(video_ids) > 1:
            safe_theme = "".join([c if c.isalnum() else "_" for c in (theme or "random")])
            file_name = f"megablob_{safe_theme}_{timestamp}.json"
        else:
            file_name = f"comments_{video_ids[0]}_{timestamp}.json"
        
        json_data = json.dumps(comments_data, ensure_ascii=False, indent=4)

        if upload_to_cloud:
            # Save to Azure Blob Storage
            blob_service_client = BlobServiceClient.from_connection_string(azure_conn_str)
            container_name = "youtube-comments" 
            
            container_client = blob_service_client.get_container_client(container_name)
            if not container_client.exists():
                container_client.create_container()

            blob_client = blob_service_client.get_blob_client(container=container_name, blob=file_name)
            blob_client.upload_blob(json_data, overwrite=True)
            save_message = f"Azure Blob Storage as '{file_name}'"
        else:
            # Save locally to local_data_lake/ directory
            local_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'local_data_lake')
            os.makedirs(local_dir, exist_ok=True)
            file_path = os.path.join(local_dir, file_name)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(json_data)
            save_message = f"local file '{file_path}'"

        return func.HttpResponse(
            f"Success: Extracted {len(comments_data)} comments from {len(video_ids)} video(s) and saved to {save_message}.",
            status_code=200
        )
        
    except Exception as e:
        logging.error(f"Error processing the main request: {str(e)}")
        return func.HttpResponse(
             f"An error occurred: {str(e)}",
             status_code=500
        )

