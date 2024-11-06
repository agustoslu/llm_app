"""
Based on https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/video-understanding
"""

from dataclasses import dataclass
from logging import getLogger
from pathlib import Path
from typing import Literal
from google.cloud import storage
import proto
from vertexai.generative_models import (
    GenerativeModel,
    Part,
    HarmCategory,
    HarmBlockThreshold,
    GenerationResponse,
)

import vertexai

logger = getLogger(__name__)

project_id = "css-lehrbereich"  # from google cloud console
frankfurt = "europe-west3"  # https://cloud.google.com/about/locations#europe
bucket_name = "css-temp-bucket-for-vertex"

_pro = "models/gemini-1.5-pro"
_flash = "models/gemini-1.5-flash"
available_models = [_pro, _flash]


@dataclass
class Request:
    media_files: list[Path]
    model_name: Literal[_pro, _flash] = _pro
    prompt: str = "Describe this video in detail."

    def fetch_media_description(self) -> str:
        return fetch_media_description(self)


def fetch_media_description(req: Request) -> str:
    # TODO: Always delete the video in the end. Perhaps use finally block.
    blobs = _upload_files(files=req.media_files)

    vertexai.init(project=project_id, location=frankfurt)
    model = GenerativeModel(req.model_name)

    prompt = req.prompt
    logger.info("Calling the Google API. model_name='%s'", req.model_name)
    contents = [
        Part.from_uri(f"gs://{bucket_name}/{b.name}", mime_type=mime_type(b.name))
        for b in blobs
    ]
    contents.append(prompt)
    response: GenerationResponse = model.generate_content(
        contents=contents,
        generation_config={"temperature": 0.0},
        safety_settings=_block_nothing(),
    )
    logger.info("Token usage: %s", proto.Message.to_dict(response.usage_metadata))

    if len(response.candidates) == 0:
        raise ResponseRefusedException(
            "No candidates in response. prompt_feedback='%s'" % response.prompt_feedback
        )

    enum = type(response.candidates[0].finish_reason)
    if response.candidates[0].finish_reason in {enum.SAFETY, enum.PROHIBITED_CONTENT}:
        raise UnsafeResponseError(safety_ratings=response.candidates[0].safety_ratings)

    for blob in blobs:
        blob.delete()
    logger.info("Deleted %d blob(s)", len(blobs))

    return response.text


def mime_type(file_name: str) -> str:
    mapping = {
        ".txt": "text/plain",
        ".jpg": "image/jpeg",
        ".png": "image/png",
        ".flac": "audio/flac",
        ".mp3": "audio/mpeg",
        ".mp4": "video/mp4",
    }
    for ext, mime in mapping.items():
        if file_name.endswith(ext):
            return mime
    raise ValueError(f"Unknown mime type for file: {file_name}")


def _upload_files(files: list[Path]) -> list[storage.Blob]:
    logger.info("Uploading %d file(s)", len(files))
    client = storage.Client(project=project_id)
    bucket = client.bucket(bucket_name)
    blobs = []
    for file in files:
        blob = bucket.blob(file.name)
        blobs.append(blob)
        if not blob.exists():
            blob.upload_from_filename(str(file), if_generation_match=0)
    logger.info("Completed uploading %d file(s)", len(files))
    return blobs


def _block_nothing() -> dict[HarmCategory, HarmBlockThreshold]:
    return {
        HarmCategory.HARM_CATEGORY_UNSPECIFIED: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY: HarmBlockThreshold.BLOCK_NONE,
    }


class UnsafeResponseError(Exception):
    def __init__(self, safety_ratings: list) -> None:
        super().__init__(
            "The response was blocked by Google due to safety reasons. Categories: %s"
            % safety_ratings
        )
        self.safety_categories = safety_ratings


class ResponseRefusedException(Exception):
    pass
