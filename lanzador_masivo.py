import requests
import time
import logging

# Configurar el logging básico para ver el progreso en la consola
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# TODO: Sustituye esta URL por la URL real de tu Azure Function cuando esté desplegada.
# Ejemplo: "https://isma-youtube-tfm.azurewebsites.net/api/extract_youtube_comments?code=TuCodigoDeSeguridad"
URL_AZURE = "http://localhost:7071/api/extract_youtube_comments" 

TOTAL_PETICIONES = 10
TIEMPO_ESPERA_SEGUNDOS = 4

def iniciar_lanzador():
    logging.info(f"Iniciando lanzador masivo hacia: {URL_AZURE}")
    logging.info(f"Se van a realizar {TOTAL_PETICIONES} peticiones.")
    logging.info("-" * 40)
    
    exitos = 0
    errores = 0

    for i in range(1, TOTAL_PETICIONES + 1):
        try:
            # Hacer la petición GET a la función
            response = requests.get(URL_AZURE, timeout=120)  # Timeout alto por si la función tarda mucho en extraer
            
            # Comprobar el código de estado HTTP
            if response.status_code == 200:
                logging.info(f"Petición {i}/{TOTAL_PETICIONES}... Estado: {response.status_code} OK")
                exitos += 1
            else:
                logging.warning(f"Petición {i}/{TOTAL_PETICIONES}... Estado: {response.status_code} - {response.text[:50]}")
                errores += 1
                
        except requests.exceptions.Timeout:
            logging.error(f"Petición {i}/{TOTAL_PETICIONES}... Error: Timeout excedido (la función tardó demasiado).")
            errores += 1
        except requests.exceptions.ConnectionError:
            logging.error(f"Petición {i}/{TOTAL_PETICIONES}... Error: Microcorte de internet o servidor inalcanzable.")
            errores += 1
        except Exception as e:
            logging.error(f"Petición {i}/{TOTAL_PETICIONES}... Error inesperado: {str(e)[:50]}")
            errores += 1
            
        # Esperar 2 segundos antes de la siguiente petición para no saturar la función
        if i < TOTAL_PETICIONES:
            time.sleep(TIEMPO_ESPERA_SEGUNDOS)

    # Resumen final
    logging.info("-" * 40)
    logging.info(f"Ejecución terminada. Éxitos: {exitos} | Errores: {errores}")

if __name__ == "__main__":
    iniciar_lanzador()
