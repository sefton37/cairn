#!/usr/bin/env python3
"""Generate 12 test user profile databases for Talking Rock.

Each profile gets its own talkingrock.db in tools/test_profiles/{profile_id}/.

Usage:
    python3 tools/generate_test_profiles.py
"""

import sys
from pathlib import Path

# Ensure the tools directory is importable
sys.path.insert(0, str(Path(__file__).parent))

from testgen.generator import generate_profile
from testgen.profiles_1 import PROFILES_1
from testgen.profiles_2 import PROFILES_2
from testgen.profiles_3 import PROFILES_3

OUTPUT_DIR = Path(__file__).parent / "test_profiles"


def main():
    all_profiles = PROFILES_1 + PROFILES_2 + PROFILES_3
    print(f"Generating {len(all_profiles)} test profiles in {OUTPUT_DIR}/\n")

    for i, profile in enumerate(all_profiles, 1):
        name = profile["identity"]["full_name"]
        dept = profile["identity"]["department"]
        pid = profile["id"]
        print(f"[{i:2d}/12] {name} ({dept}) → {pid}/")

        stats = generate_profile(profile, OUTPUT_DIR)

        print(f"        {stats['acts']} acts, {stats['scenes']} scenes, "
              f"{stats['conversations']} conversations, {stats['messages']} messages, "
              f"{stats['memories']} memories, {stats['emails']} emails, "
              f"{stats['calendar']} calendar events, {stats['blocks']} blocks")

    print(f"\nDone. {len(all_profiles)} profiles generated in {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
