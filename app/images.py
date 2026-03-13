from imagekitio import ImageKit
from dotenv import load_dotenv
import os

load_dotenv()

imageKit = ImageKit(
    private_key=os.getenv("IMAGEKIT_PRIVATE_KEY")
)

URL_ENDPOINT = os.environ.get("IMAGEKIT_URL_ENDPOINT")
