"""Fitur opsional ``docgen`` di luar pipeline inti.

Setiap subpackage fitur memiliki API sendiri dan tidak boleh mengubah urutan
stage kanonik. Integrasi ke pipeline dilakukan oleh pemilik ``pipeline.py``.
"""

from __future__ import annotations
