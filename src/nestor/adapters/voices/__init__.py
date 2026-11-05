"""Voice models: `sherpa_onnx` turns speech into voiceprints on the CPU, with a model of its catalogue or a file."""

from nestor.adapters.voices.sherpa_onnx import CATALOGUE, Catalogued, SherpaOnnxVoice, SherpaOnnxVoiceSettings, plugin

__all__ = ["CATALOGUE", "Catalogued", "SherpaOnnxVoice", "SherpaOnnxVoiceSettings", "plugin"]
