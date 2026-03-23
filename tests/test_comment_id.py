import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# Asegurar que la raíz del proyecto y 'src' sean importables
root_path = Path(__file__).parent.parent
sys.path.append(str(root_path))
if str(root_path / "src") not in sys.path:
    sys.path.append(str(root_path / "src"))

from src.services.youtube_service import YouTubeService

class TestCommentStructure(unittest.TestCase):
    def setUp(self):
        # Inicializamos el servicio con valores de prueba
        self.service = YouTubeService(api_key="test", global_limit=1)
        
    def test_comment_id_field_is_present(self):
        """
        Verifica que el diccionario de comentario devuelto por fetch_comments
        contiene el campo 'comment_id'.
        """
        # Mock de respuesta de búsqueda de videos
        self.service._execute_search = MagicMock(return_value={"items": [{"id": {"videoId": "fake_video"}}]})
        
        # Mock de respuesta de comentarios de YouTube
        mock_response = {
            "items": [
                {
                    "id": "ID_DE_PRUEBA_123",
                    "snippet": {
                        "topLevelComment": {
                            "snippet": {
                                "textDisplay": "Hola, esto es una prueba",
                                "publishedAt": "2025-03-22T22:00:00Z",
                                "authorDisplayName": "Tester",
                                "likeCount": 10
                            }
                        }
                    }
                }
            ]
        }
        self.service._execute_comment_page = MagicMock(return_value=mock_response)
        
        # Mock de fechas de publicación
        self.service.get_video_publish_dates = MagicMock(return_value={"fake_video": "2025-01-01T00:00:00Z"})

        # Ejecutamos la extracción (usando checkpoints={} para evitar efectos secundarios)
        comments = self.service.fetch_comments(
            video_ids=["fake_video"], 
            theme="test", 
            is_short=False, 
            checkpoints={}
        )
        
        # Validaciones
        self.assertTrue(len(comments) > 0, "No se extrajeron comentarios")
        first_record = comments[0]
        
        self.assertIn("comment_id", first_record, "El campo 'comment_id' no está en el registro")
        self.assertEqual(first_record["comment_id"], "ID_DE_PRUEBA_123")
        
        print("\n✅ Verificación exitosa: 'comment_id' encontrado.")

if __name__ == "__main__":
    unittest.main()
