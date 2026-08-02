"""
tests/test_utils.py

Unit tests for utils.py -- URL validation and filename sanitization.
These are pure-function tests: no network calls, no yt-dlp, no Flask
server needed. Run with: pytest

Several of these are REGRESSION TESTS for real bugs found during
manual testing (see comments) -- they exist specifically so those
exact bugs can never silently reappear after a future code change.
"""

import sys
from pathlib import Path

# Allow running `pytest` from the project root without extra config.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from utils import validate_youtube_url, sanitize_filename, InvalidURLError


class TestValidateYoutubeUrl:

    def test_accepts_standard_watch_url(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert validate_youtube_url(url) == url

    def test_accepts_youtube_short_link(self):
        url = "https://youtu.be/dQw4w9WgXcQ"
        assert validate_youtube_url(url) == url

    def test_accepts_mobile_youtube_domain(self):
        url = "https://m.youtube.com/watch?v=dQw4w9WgXcQ"
        assert validate_youtube_url(url) == url

    def test_rejects_non_youtube_domain(self):
        with pytest.raises(InvalidURLError):
            validate_youtube_url("https://vimeo.com/12345")

    def test_rejects_malformed_url(self):
        with pytest.raises(InvalidURLError):
            validate_youtube_url("not a url at all")

    def test_rejects_empty_string(self):
        with pytest.raises(InvalidURLError):
            validate_youtube_url("")

    def test_rejects_dangerous_scheme(self):
        with pytest.raises(InvalidURLError):
            validate_youtube_url("javascript:alert(1)")

    def test_rejects_bare_domain_with_no_video(self):
        with pytest.raises(InvalidURLError):
            validate_youtube_url("https://www.youtube.com")

    def test_rejects_bare_playlist_page(self):
        # A genuine playlist link with no specific video -- should
        # still be rejected, this app only downloads single videos.
        url = "https://www.youtube.com/playlist?list=PLsomeplaylistid"
        with pytest.raises(InvalidURLError):
            validate_youtube_url(url)

    def test_accepts_watch_url_with_playlist_context(self):
        # A specific video that happens to also carry playlist
        # context (v= AND list= both present) -- must be accepted.
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLxxx&index=3"
        assert validate_youtube_url(url) == url

    def test_accepts_short_link_with_playlist_context(self):
        # REGRESSION TEST: youtu.be short links carry the video ID in
        # the URL PATH, not a "v=" query param. An earlier version of
        # this validator incorrectly rejected
        # "youtu.be/<id>?list=<playlist>" as a bare playlist, because
        # it only checked for "v" in the query string. This must
        # never happen again.
        url = "https://youtu.be/dQw4w9WgXcQ?list=PLxxx"
        assert validate_youtube_url(url) == url

    def test_accepts_short_link_with_mix_radio_playlist(self):
        # REGRESSION TEST: YouTube "Mix"/Radio playlists use a list=
        # ID prefixed with "RD". These must be treated identically to
        # any other playlist context on a single-video link -- i.e.
        # accepted here at the validation layer. (The actual hang bug
        # this URL shape caused was in downloader.list_qualities()
        # missing noplaylist=True, not in validation -- but this test
        # locks in that validation, at least, was never the problem.)
        url = "https://youtu.be/8of5w7RgcTc?list=RD8of5w7RgcTc"
        assert validate_youtube_url(url) == url

    def test_rejects_url_over_length_limit(self):
        long_url = "https://www.youtube.com/watch?v=" + "a" * 3000
        with pytest.raises(InvalidURLError):
            validate_youtube_url(long_url)


class TestSanitizeFilename:

    def test_strips_path_traversal_attempt(self):
        result = sanitize_filename("../../etc/passwd")
        assert "/" not in result
        assert ".." not in result or result.count(".") <= 2

    def test_removes_illegal_characters(self):
        result = sanitize_filename('My Video: Best Ever?! (2024)')
        for bad_char in [":", "?", "*", "<", ">", "|", '"']:
            assert bad_char not in result

    def test_strips_leading_trailing_dots_and_spaces(self):
        result = sanitize_filename("   ...leading dots and spaces...   ")
        assert result == result.strip(" .")

    def test_empty_input_falls_back_to_default(self):
        assert sanitize_filename("") == "download"

    def test_truncates_excessively_long_names(self):
        result = sanitize_filename("a" * 500, max_length=150)
        assert len(result) <= 150


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))