import azure.functions as func
import logging
import os
import json
import random
from googleapiclient.discovery import build
from azure.storage.blob import BlobServiceClient
from datetime import datetime

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

@app.route(route="extract_youtube_comments")
def extract_youtube_comments(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    youtube_api_key = os.environ.get("YOUTUBE_API_KEY")
    azure_conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    
    if not youtube_api_key or not azure_conn_str:
        return func.HttpResponse(
             "Faltan las variables de entorno 'YOUTUBE_API_KEY' o 'AZURE_STORAGE_CONNECTION_STRING'.",
             status_code=500
        )

    try:
        youtube = build('youtube', 'v3', developerKey=youtube_api_key)

        # Get video_id from query string or body
        video_id = req.params.get('video_id')
        if not video_id:
            try:
                req_body = req.get_json()
                video_id = req_body.get('video_id')
            except ValueError:
                pass
        
        # Modo Automático: Si no se proporciona un ID, buscar uno en inglés de forma aleatoria.
        if not video_id:
            queries = [
                # Temas Tech & Gaming
                'gameplay', 'tech review', 'unboxing', 'pc build', 'coding', 'software development', 'indie game', 'speedrun', 'playthrough', 'hardware test', 'smartphone review', 'VR headset', 'AI explained',
                # Entretenimiento & Vlogs
                'vlog', 'day in the life', 'documentary', 'funny fails', 'stand up comedy', 'live performance', 'magic trick', 'movie breakdown', 'tv show review', 'celebrity interview', 'conspiracy theory',
                # Educación & Ciencia
                'how to', 'tutorial', 'history explained', 'science experiment', 'space exploration', 'math problem', 'physics', 'learning English', 'language learning', 'psychology facts', 'biography',
                # Música & Arte
                'music video', 'acoustic cover', 'live concert', 'guitar tutorial', 'beat making', 'drawing timelapse', 'oil painting', 'digital art', 'photography tips', 'cinematography',
                # Deportes & Salud
                'fitness routine', 'home workout', 'yoga for beginners', 'bodybuilding', 'football highlights', 'basketball game', 'sports highlights', 'martial arts', 'running tips', 'calisthenics',
                # Comida & Viajes
                'street food', 'cooking recipe', 'baking', 'restaurant review', 'tasting snacks', 'travel vlog', 'backpacking', 'hidden gems', 'vacation vlog', 'tourist guide',
                # Otros temas y combinaciones locas
                'crypto news', 'stock market', 'finance tips', 'real estate', 'car review', 'restoration projects', 'woodworking', 'DIY', 'life hacks', 'camping', 'fishing', 'pet vlog', 'cute dogs', 'cat videos',
                'asmr', 'mukbang', 'true crime', 'paranormal', 'urban exploration', 'abandoned places',
                # Letras y fragmentos al azar para pescar cualquier cosa
                'a', 'the', 'is', 'how', 'what', 'when', 'why', 'who', 'best', 'worst', 'top 10', 'vs', 'explained', 'full episode'
            ]
            from datetime import timedelta, datetime

            random_query = random.choice(queries)

            # Generar una fecha aleatoria desde 2025 hasta hoy
            start_date = datetime(2025, 1, 1)
            end_date = datetime.now()
            delta = end_date - start_date
            random_days = random.randrange(max(1, delta.days)) # Evitar error si ejecutamos el mismo día
            random_published_after = (start_date + timedelta(days=random_days)).strftime('%Y-%m-%dT%H:%M:%SZ')
            
            logging.info(f"Modo automático: Buscando '{random_query}' con fecha min {random_published_after}...")

            search_request = youtube.search().list(
                part="snippet",
                q=random_query,
                type="video",
                relevanceLanguage="en",
                publishedAfter=random_published_after,
                maxResults=50 # Pedimos 50 y escogemos 1 al azar
            )
            search_response = search_request.execute()
            
            if 'items' in search_response and search_response['items']:
                random_item = random.choice(search_response['items'])
                video_id = random_item['id']['videoId']
                logging.info(f"Vídeo seleccionado aleatoriamente: {video_id}")
            else:
                return func.HttpResponse("No se encontraron vídeos automáticos para probar.", status_code=404)

        # 1. Extraer comentarios de YouTube
        # youtube ya se inicializó arriba con: youtube = build('youtube', 'v3', developerKey=youtube_api_key)

        comments_data = []
        request = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=100
        )
        
        while request is not None and len(comments_data) < 1500:
            response = request.execute()
            
            for item in response['items']:
                if len(comments_data) >= 1500:
                    break
                comment = item['snippet']['topLevelComment']['snippet']
                comments_data.append({
                    'author': comment.get('authorDisplayName'),
                    'text': comment.get('textDisplay'), # Comentario
                    'likeCount': comment.get('likeCount', 0), # Likes
                    'publishedAt': comment.get('publishedAt') # Fecha de publicación
                })
            
            # Paginación: si hay más comentarios, obtener la siguiente página
            if 'nextPageToken' in response and len(comments_data) < 1500:
                request = youtube.commentThreads().list_next(
                    previous_request=request, 
                    previous_response=response
                )
            else:
                break
                
        # 2. Guardar los datos en Azure Blob Storage
        blob_service_client = BlobServiceClient.from_connection_string(azure_conn_str)
        container_name = "youtube-comments" # Puedes cambiar el nombre del contenedor si lo necesitas
        
        # Crear contenedor si no existe
        container_client = blob_service_client.get_container_client(container_name)
        if not container_client.exists():
            container_client.create_container()

        # Crear un nombre de archivo único
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        blob_name = f"comments_{video_id}_{timestamp}.json"
        
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
        
        # Convertir datos a JSON y subir al Blob Storage
        json_data = json.dumps(comments_data, ensure_ascii=False, indent=4)
        blob_client.upload_blob(json_data, overwrite=True)

        return func.HttpResponse(
            f"Éxito: Se extrajeron {len(comments_data)} comentarios del vídeo '{video_id}' y se guardaron en '{blob_name}'.",
            status_code=200
        )
        
    except Exception as e:
        logging.error(f"Error procesando el vídeo {video_id}: {str(e)}")
        return func.HttpResponse(
             f"Ha ocurrido un error: {str(e)}",
             status_code=500
        )
