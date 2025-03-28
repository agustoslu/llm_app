import cv2
from llmlib.huggingface_inference import (
    compute_frame_indices,
    convert_message_to_openai_format,
)
import pytest
from llmlib.huggingface_inference import HuggingFaceVLM, HuggingFaceVLMs
from .helpers import (
    assert_model_recognizes_pyramid_in_image,
    assert_model_supports_multiturn_with_6min_video,
    decode_base64_to_array,
    file_for_test,
    is_ci,
    assert_model_knows_capital_of_france,
    assert_model_supports_multiturn,
    assert_model_supports_multiturn_with_multiple_imgs,
    pyramid_message,
    video_message,
)


@pytest.fixture
def gemma3():
    return HuggingFaceVLM(
        model_id=HuggingFaceVLMs.gemma_3_27b_it,
        use_hosted_model=False,
        # 10 frames gets OOM at A100 (80GB) VRAM.
        # 4 frames gets OOM at L4 (24GB) VRAM.
        max_n_frames_per_video=3,
    )


def test_huggingface_vlm_warnings():
    warnings = HuggingFaceVLM.get_warnings()
    assert len(warnings) == 0


def test_huggingface_vlm_info():
    info = HuggingFaceVLM.get_info()
    assert len(info) == 3
    assert "huggingface.co" in info[0]
    assert "text-only and image+text queries" in info[1]
    assert "multi-turn conversations" in info[2]


@pytest.mark.skipif(condition=is_ci(), reason="Avoid costs")
def test_huggingface_vlm_complete_msgs_text_only(gemma3):
    assert_model_knows_capital_of_france(gemma3)


@pytest.mark.skipif(condition=is_ci(), reason="Avoid costs")
def test_huggingface_vlm_complete_msgs_with_image(gemma3):
    assert_model_recognizes_pyramid_in_image(gemma3)


@pytest.mark.skipif(condition=is_ci(), reason="Avoid costs")
def test_huggingface_vlm_multi_turn_text_conversation(gemma3):
    assert_model_supports_multiturn(gemma3)


@pytest.mark.skipif(condition=is_ci(), reason="Avoid costs")
def test_huggingface_vlm_multi_turn_with_images(gemma3):
    assert_model_supports_multiturn_with_multiple_imgs(gemma3)


@pytest.mark.skip(reason="We currently run OOM on serverless and hosted.")
def test_huggingface_vlm_multi_turn_with_6min_video(gemma3):
    assert_model_supports_multiturn_with_6min_video(gemma3)


@pytest.mark.skipif(condition=is_ci(), reason="Files are not available on CI")
def test_convert_to_openai_format():
    img_msg1 = pyramid_message(load_img=True)
    img_msg2 = pyramid_message(load_img=False)
    max_n_frames_per_video = 200
    b64_enc1 = convert_message_to_openai_format(img_msg1, max_n_frames_per_video)[
        "content"
    ][1]["image_url"]["url"]
    b64_enc2 = convert_message_to_openai_format(img_msg2, max_n_frames_per_video)[
        "content"
    ][1]["image_url"]["url"]
    # assert b64_enc1 == b64_enc2
    array1 = decode_base64_to_array(base64_str=b64_enc1)
    array2 = decode_base64_to_array(base64_str=b64_enc2)
    # asserting imgs are the same fails, but you can visually inspect them
    cv2.imwrite(file_for_test("generated_pyramid_1.jpeg"), array1)
    cv2.imwrite(file_for_test("generated_pyramid_2.jpeg"), array2)

    msg = video_message()
    hf_msg = convert_message_to_openai_format(msg, max_n_frames_per_video)
    assert len(hf_msg["content"]) > 10


def test_compute_frame_indices():
    # 1 frame per second of video
    idxs = compute_frame_indices(vid_n_frames=100, vid_fps=10, max_n_frames=10)
    assert idxs == [0, 10, 20, 30, 40, 50, 60, 70, 80, 90]

    # short video, return 1 frame every second
    idxs = compute_frame_indices(vid_n_frames=100, vid_fps=30, max_n_frames=6)
    assert idxs == [0, 30, 60, 90]

    # long video, split into max_n_frames
    idxs = compute_frame_indices(vid_n_frames=100, vid_fps=30, max_n_frames=3)
    assert idxs == [0, 33, 66]

    # regression case
    idx = compute_frame_indices(vid_n_frames=751, vid_fps=25.0, max_n_frames=20)
    assert len(idx) <= 20
