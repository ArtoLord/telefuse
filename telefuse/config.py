import pydantic


class AppConfig(pydantic.BaseModel):
    api_id: int = 919672
    api_hash: str = "9b85feea20823c6a28ad50d5a22ce3b0"
    