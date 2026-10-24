# ABOUTME: The BanTopics zero-shot classifier weights as an image, so the guard build does not depend on
# ABOUTME: Hugging Face staying reachable. Contents only: no shell, no libc, nothing to execute.
#
# WHY
#
# The on-topic guard (Unleash_an_Agent_Watch_It_Burn#455) runs LLM Guard's BanTopics scanner. With
# `lazy_load: false` a scanner whose model is missing stops the API from starting, and behind a
# default-deny egress policy the Hub download it would otherwise attempt fails, so the whole guard,
# prompt-injection classifier included, would fail closed. The weights are mirrored here for the same
# reason as model/ (#414): the guard image copies them across with COPY --from, pinned by digest.
#
# PROVENANCE, verified 2026-10-24
#
#   repo      MoritzLaurer/deberta-v3-base-zeroshot-v2.0   (MIT)
#   revision  8e7e5af5983a0ddb1a5b45a38b129ab69e2258e8
#   files     added_tokens.json        sha256 dc046d04c9b0ada7ae6f1dc89c465801799acdf0c9a6aab8c15a1b2d5ca4e91f
#             config.json              sha256 a68162c0b02cd39759732b33d26ee2868cb64701b0b9255fee4f55fd9d5609f4
#             model.onnx               sha256 d46fa6c1addc598abd34af8651120291f51417ddfce45b9d5f70bc32d3efa81c
#             special_tokens_map.json  sha256 b2f1b2f15f29a6b6d9d6ea4eca1675d2c231a71477f151d48f79cc83a625ba21
#             spm.model                sha256 c679fbf93643d19aab7ee10c0b99e460bdbc02fedf34b92b05af343b4af586fd
#             tokenizer.json           sha256 bfead76cd475f67849a6710fdd16497f75732773e4d90e40d3b5bb5d3f031df9
#             tokenizer_config.json    sha256 f5a1a74a632c0e9225e09a21ddf60c2e70ef5d3bfc1f261a24fd8ddab27254d2
#
# This is the revision llm-guard 0.3.16 pins for BanTopics (MODEL_DEBERTA_BASE_V2 in
# llm_guard/input_scanners/ban_topics.py). The files are its onnx/ directory. For model.onnx and
# spm.model the Hugging Face API publishes the LFS sha256, and it agrees with the hash computed from the
# downloaded bytes. The other five are plain git blobs, whose git object ids from the API agree with
# `git hash-object` of the same bytes; their sha256 above was computed from those bytes.
#
# Unlike model/, there is no earlier image of ours to copy these bytes from, so this build is the one
# place that reads the Hub. Every ADD carries its sha256 and the builder refuses a file that differs,
# so a rebuild either produces these exact bytes or fails. The files land at the top level of /model,
# which is the layout `model_path` loads with local_files_only.
#
# Build and push (from this repo's root):
#   docker build -t ghcr.io/peopleforrester/watch-it-burn:llm-guard-model-zeroshot-8e7e5af5 model-zero-shot
#   docker push ghcr.io/peopleforrester/watch-it-burn:llm-guard-model-zeroshot-8e7e5af5
#
# Then pin the pushed digest in the guard Dockerfile.

FROM scratch

LABEL org.opencontainers.image.source=https://github.com/peopleforrester/Unleash_an_Agent_Watch_It_Burn
LABEL org.opencontainers.image.description="deberta-v3-base-zeroshot-v2.0 ONNX weights, revision 8e7e5af5983a0ddb1a5b45a38b129ab69e2258e8, mirrored"
LABEL org.opencontainers.image.licenses=MIT
LABEL org.opencontainers.image.title="llm-guard BanTopics zero-shot classifier weights"

ADD --checksum=sha256:dc046d04c9b0ada7ae6f1dc89c465801799acdf0c9a6aab8c15a1b2d5ca4e91f --chmod=644 https://huggingface.co/MoritzLaurer/deberta-v3-base-zeroshot-v2.0/resolve/8e7e5af5983a0ddb1a5b45a38b129ab69e2258e8/onnx/added_tokens.json /model/added_tokens.json
ADD --checksum=sha256:a68162c0b02cd39759732b33d26ee2868cb64701b0b9255fee4f55fd9d5609f4 --chmod=644 https://huggingface.co/MoritzLaurer/deberta-v3-base-zeroshot-v2.0/resolve/8e7e5af5983a0ddb1a5b45a38b129ab69e2258e8/onnx/config.json /model/config.json
ADD --checksum=sha256:d46fa6c1addc598abd34af8651120291f51417ddfce45b9d5f70bc32d3efa81c --chmod=644 https://huggingface.co/MoritzLaurer/deberta-v3-base-zeroshot-v2.0/resolve/8e7e5af5983a0ddb1a5b45a38b129ab69e2258e8/onnx/model.onnx /model/model.onnx
ADD --checksum=sha256:b2f1b2f15f29a6b6d9d6ea4eca1675d2c231a71477f151d48f79cc83a625ba21 --chmod=644 https://huggingface.co/MoritzLaurer/deberta-v3-base-zeroshot-v2.0/resolve/8e7e5af5983a0ddb1a5b45a38b129ab69e2258e8/onnx/special_tokens_map.json /model/special_tokens_map.json
ADD --checksum=sha256:c679fbf93643d19aab7ee10c0b99e460bdbc02fedf34b92b05af343b4af586fd --chmod=644 https://huggingface.co/MoritzLaurer/deberta-v3-base-zeroshot-v2.0/resolve/8e7e5af5983a0ddb1a5b45a38b129ab69e2258e8/onnx/spm.model /model/spm.model
ADD --checksum=sha256:bfead76cd475f67849a6710fdd16497f75732773e4d90e40d3b5bb5d3f031df9 --chmod=644 https://huggingface.co/MoritzLaurer/deberta-v3-base-zeroshot-v2.0/resolve/8e7e5af5983a0ddb1a5b45a38b129ab69e2258e8/onnx/tokenizer.json /model/tokenizer.json
ADD --checksum=sha256:f5a1a74a632c0e9225e09a21ddf60c2e70ef5d3bfc1f261a24fd8ddab27254d2 --chmod=644 https://huggingface.co/MoritzLaurer/deberta-v3-base-zeroshot-v2.0/resolve/8e7e5af5983a0ddb1a5b45a38b129ab69e2258e8/onnx/tokenizer_config.json /model/tokenizer_config.json
COPY LICENSE.model /LICENSE
