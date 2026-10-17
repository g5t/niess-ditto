# SPDX-FileCopyrightText: 2026-present Gregory Tucker <gregory.tucker@ess.eu>
#
# SPDX-License-Identifier: MIT
"""NICOS devices for DITTO digital instrument models.

The device classes are imported by NICOS from their modules (``niess_ditto.motor`` and
so on), so nothing is imported here: the translator and setup generator are usable
without NICOS' device machinery loaded.
"""
from .__about__ import __version__

__all__ = ['__version__']
