"""
Qleam — Speech Transcriber
Transcribes audio to text using AWS Transcribe.
Detects words, sentences, and provides word-level analysis.

Supports:
- Real-time transcription via AWS Transcribe
- Word count and sentence detection
- Language detection
- Confidence scoring per word
"""
import json
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

import boto3

logger = logging.getLogger(__name__)

# Configuration
TRANSCRIBE_TIMEOUT_SECONDS = int(os.environ.get("TRANSCRIBE_TIMEOUT_SECONDS", "30"))
S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME", "qleam-dev-audio-storage")
TRANSCRIBE_LANGUAGE_CODE = os.environ.get("TRANSCRIBE_LANGUAGE_CODE", "en-US")
ENABLE_LANGUAGE_ID = os.environ.get("ENABLE_TRANSCRIBE_LANGUAGE_ID", "true").lower() == "true"

# Supported languages for auto-detection
AUTO_DETECT_LANGUAGES = ["en-US", "es-US", "fr-FR", "de-DE", "it-IT", "pt-BR", "ja-JP", "ko-KR", "zh-CN", "ar-SA", "hi-IN", "bn-IN"]


def transcribe_audio(
    s3_audio_path: str,
    bucket: Optional[str] = None,
    language_code: Optional[str] = None,
    timeout_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Transcribe audio from S3 using AWS Transcribe.

    Args:
        s3_audio_path: S3 key for the audio file
        bucket: S3 bucket (defaults to env var)
        language_code: Language code (defaults to auto-detect)
        timeout_seconds: Max wait time

    Returns:
        {
            "text": str,               # Full transcript
            "words": [                  # Word-level details
                {"word": str, "confidence": float, "start_time": float, "end_time": float}
            ],
            "word_count": int,
            "sentences": [str],         # Detected sentences
            "sentence_count": int,
            "language_code": str,
            "overall_confidence": float,
            "transcribe_attempted": True,
            "success": bool,
        }
    """
    bucket = bucket or S3_BUCKET_NAME
    timeout = timeout_seconds or TRANSCRIBE_TIMEOUT_SECONDS

    try:
        transcribe_client = boto3.client("transcribe")
        job_name = f"qleam-{uuid.uuid4().hex[:12]}"
        media_uri = f"s3://{bucket}/{s3_audio_path}"

        # Determine media format from extension
        ext = s3_audio_path.rsplit(".", 1)[-1].lower() if "." in s3_audio_path else "webm"
        media_format_map = {
            "webm": "webm",
            "mp3": "mp3",
            "wav": "wav",
            "flac": "flac",
            "ogg": "ogg",
            "mp4": "mp4",
            "m4a": "mp4",
        }
        media_format = media_format_map.get(ext, "webm")

        # Build transcription job params
        job_params = {
            "TranscriptionJobName": job_name,
            "Media": {"MediaFileUri": media_uri},
            "MediaFormat": media_format,
            "OutputBucketName": bucket,
            "OutputKey": f"transcripts/{job_name}.json",
            "Settings": {
                "ShowSpeakerLabels": False,
                "ShowAlternatives": False,
            },
        }

        # Language identification or fixed language
        if ENABLE_LANGUAGE_ID and not language_code:
            job_params["IdentifyLanguage"] = True
            job_params["LanguageOptions"] = AUTO_DETECT_LANGUAGES
        else:
            job_params["LanguageCode"] = language_code or TRANSCRIBE_LANGUAGE_CODE

        transcribe_client.start_transcription_job(**job_params)
        logger.info(f"Started transcription job: {job_name}")

        # Poll for completion
        start_time = time.time()
        while time.time() - start_time < timeout:
            status = transcribe_client.get_transcription_job(
                TranscriptionJobName=job_name
            )
            job_status = status["TranscriptionJob"]["TranscriptionJobStatus"]

            if job_status == "COMPLETED":
                result = _parse_transcription_result(status, bucket, job_name)
                _cleanup_transcription_job(transcribe_client, job_name)
                return result
            elif job_status == "FAILED":
                reason = status["TranscriptionJob"].get("FailureReason", "Unknown")
                logger.warning(f"Transcription failed: {reason}")
                _cleanup_transcription_job(transcribe_client, job_name)
                return _empty_result(f"Transcription failed: {reason}")

            time.sleep(2)

        # Timeout
        logger.warning(f"Transcription timed out after {timeout}s")
        _cleanup_transcription_job(transcribe_client, job_name)
        return _empty_result("Transcription timed out")

    except Exception as e:
        logger.error(f"Transcription error: {e}")
        return _empty_result(str(e))


def _parse_transcription_result(
    status: Dict,
    bucket: str,
    job_name: str,
) -> Dict[str, Any]:
    """Parse the transcription result from S3."""
    try:
        s3 = boto3.client("s3")
        output_key = f"transcripts/{job_name}.json"
        obj = s3.get_object(Bucket=bucket, Key=output_key)
        data = json.loads(obj["Body"].read().decode("utf-8"))

        # Clean up transcript file
        try:
            s3.delete_object(Bucket=bucket, Key=output_key)
        except Exception:
            pass

        results = data.get("results", {})
        transcripts = results.get("transcripts", [])
        items = results.get("items", [])

        # Extract full text
        full_text = ""
        if transcripts:
            full_text = transcripts[0].get("transcript", "").strip()

        # Extract words with confidence
        words = []
        for item in items:
            if item.get("type") == "pronunciation":
                alts = item.get("alternatives", [{}])
                best = alts[0] if alts else {}
                word_entry = {
                    "word": best.get("content", ""),
                    "confidence": float(best.get("confidence", 0)),
                    "start_time": float(item.get("start_time", 0)),
                    "end_time": float(item.get("end_time", 0)),
                }
                if word_entry["word"]:
                    words.append(word_entry)

        # Detect language
        job_data = status.get("TranscriptionJob", {})
        language = job_data.get("LanguageCode", "")
        if not language:
            lang_codes = job_data.get("IdentifiedLanguageScore")
            if isinstance(lang_codes, dict) and lang_codes:
                language = max(lang_codes, key=lang_codes.get)

        # Split into sentences
        sentences = _split_sentences(full_text)

        # Overall confidence
        if words:
            overall_conf = sum(w["confidence"] for w in words) / len(words)
        else:
            overall_conf = 0.0

        return {
            "text": full_text,
            "words": words,
            "word_count": len(words),
            "sentences": sentences,
            "sentence_count": len(sentences),
            "language_code": language,
            "overall_confidence": round(overall_conf, 3),
            "transcribe_attempted": True,
            "success": len(full_text) > 0,
        }
    except Exception as e:
        logger.error(f"Failed to parse transcription result: {e}")
        return _empty_result(str(e))


def _split_sentences(text: str) -> List[str]:
    """Split transcript text into sentences."""
    if not text:
        return []
    # Simple sentence splitting on punctuation
    import re
    parts = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in parts if s.strip()]
    # If no punctuation, treat the whole text as one sentence
    if not sentences and text.strip():
        sentences = [text.strip()]
    return sentences


def _cleanup_transcription_job(client, job_name: str):
    """Clean up the transcription job."""
    try:
        client.delete_transcription_job(TranscriptionJobName=job_name)
    except Exception:
        pass


def _empty_result(reason: str = "") -> Dict[str, Any]:
    """Return an empty transcription result."""
    return {
        "text": "",
        "words": [],
        "word_count": 0,
        "sentences": [],
        "sentence_count": 0,
        "language_code": "",
        "overall_confidence": 0.0,
        "transcribe_attempted": True,
        "success": False,
        "failure_reason": reason,
    }


def analyze_words_for_display(transcript_result: Dict) -> Dict[str, Any]:
    """
    Analyze transcript words for clean display.

    Returns:
        {
            "has_words": bool,
            "has_sentences": bool,
            "display_words": [{"word": str, "count": int}],
            "display_text": str,
            "word_count": int,
            "unique_word_count": int,
            "avg_word_confidence": float,
            "repetition_ratio": float,  # How much the same words repeat
        }
    """
    words = transcript_result.get("words", [])
    text = transcript_result.get("text", "")

    if not words:
        return {
            "has_words": False,
            "has_sentences": False,
            "display_words": [],
            "display_text": "",
            "word_count": 0,
            "unique_word_count": 0,
            "avg_word_confidence": 0.0,
            "repetition_ratio": 0.0,
        }

    # Count unique words (case-insensitive)
    word_counts = {}
    total_conf = 0.0
    for w in words:
        word_lower = w["word"].lower()
        word_counts[word_lower] = word_counts.get(word_lower, 0) + 1
        total_conf += w.get("confidence", 0)

    # Sort by count descending
    display_words = sorted(
        [{"word": k, "count": v} for k, v in word_counts.items()],
        key=lambda x: x["count"],
        reverse=True,
    )

    unique_count = len(word_counts)
    total_count = len(words)
    repetition = 1.0 - (unique_count / max(1, total_count))

    sentences = transcript_result.get("sentences", [])

    return {
        "has_words": total_count > 0,
        "has_sentences": len(sentences) > 1 or total_count > 3,
        "display_words": display_words,
        "display_text": text,
        "word_count": total_count,
        "unique_word_count": unique_count,
        "avg_word_confidence": round(total_conf / max(1, total_count), 3),
        "repetition_ratio": round(repetition, 3),
    }
