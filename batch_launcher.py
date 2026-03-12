import requests
import time
import logging
import random

# Configure basic logging to see progress in the console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# TODO: Replace this URL with the actual URL of your Azure Function when deployed.
# Example: "https://isma-youtube-tfm.azurewebsites.net/api/extract_youtube_comments?code=YourSecurityCode"
AZURE_URL = "http://localhost:7071/api/extract_youtube_comments" 

TOTAL_REQUESTS = 2
WAIT_TIME_SECONDS = 4

# Macro-themes specifically selected to measure critical thinking levels in comments.
# Includes a mix of expected superficial engagement (entertainment/drama), 
# analytical engagement (education/science), and highly polarized topics.
THEMES = [
    # Expected impulsive / superficial engagement
    'celebrity gossip', 
    'funny pranks', 
    'daily vlog', 
    'influencer apology',
    'gaming drama',
    'viral challenges',
    
    # Expected informational / analytical engagement
    'science documentary', 
    'history explained', 
    'video essay', 
    'philosophy lecture',
    'personal finance', 
    'tech gadget review',
    
    # Highly polarized / debate topics
    'politics debate',
    'conspiracy theory'
]

def start_launcher():
    logging.info(f"Starting batch launcher targeting: {AZURE_URL}")
    logging.info(f"{TOTAL_REQUESTS} requests will be made.")
    logging.info("-" * 40)
    
    successes = 0
    errors = 0

    # Shuffle themes entirely so we can iterate without repeating
    shuffled_themes = THEMES.copy()
    random.shuffle(shuffled_themes)

    for i in range(1, TOTAL_REQUESTS + 1):
        try:
            # If we run out of themes, reshuffle and start over
            if not shuffled_themes:
                shuffled_themes = THEMES.copy()
                random.shuffle(shuffled_themes)
                logging.info("All themes were used! Reshuffling the list to start again...")
                
            selected_theme = shuffled_themes.pop()
            
            # Parameters to send to the function in the JSON body
            payload = {
                "theme": selected_theme,
                "is_short": True,
                "upload_to_cloud": True  # Keep False to save in local_data_lake/
            }
            
            logging.info(f"Request {i}/{TOTAL_REQUESTS}... Selected theme: '{selected_theme}'")
            
            # Make the GET request to the function, sending parameters in the JSON body
            response = requests.get(AZURE_URL, json=payload, timeout=600)  # Critical timeout (10m) to handle the massive download of 10000 comments
            
            # Check the HTTP status code
            if response.status_code == 200:
                logging.info(f"Request {i}/{TOTAL_REQUESTS}... Status: {response.status_code} OK")
                successes += 1
            else:
                logging.warning(f"Request {i}/{TOTAL_REQUESTS}... Status: {response.status_code} - {response.text[:50]}")
                errors += 1
                
        except requests.exceptions.Timeout:
            logging.error(f"Request {i}/{TOTAL_REQUESTS}... Error: Timeout exceeded (the function took too long).")
            errors += 1
        except requests.exceptions.ConnectionError:
            logging.error(f"Request {i}/{TOTAL_REQUESTS}... Error: Internet micro-cut or unreachable server.")
            errors += 1
            
            # Wait a few seconds before the next request to avoid overloading the function
            # Place wait conditionally in case of connection error to still throttle
            if i < TOTAL_REQUESTS:
                time.sleep(WAIT_TIME_SECONDS)
            continue
            
        except Exception as e:
            logging.error(f"Request {i}/{TOTAL_REQUESTS}... Unexpected error: {str(e)[:50]}")
            errors += 1
            
        # Wait a few seconds before the next request to avoid overloading the function
        if i < TOTAL_REQUESTS:
            time.sleep(WAIT_TIME_SECONDS)

    # Final summary
    logging.info("-" * 40)
    logging.info(f"Execution finished. Successes: {successes} | Errors: {errors}")

if __name__ == "__main__":
    start_launcher()
