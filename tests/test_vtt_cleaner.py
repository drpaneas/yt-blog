import textwrap
import unittest

from vtt_cleaner import clean_vtt_text


class CleanVttTextTests(unittest.TestCase):
    def test_removes_vtt_noise_and_merges_overlapping_cues(self) -> None:
        vtt_text = textwrap.dedent(
            """\
            WEBVTT
            Kind: captions
            Language: en

            00:00:00.000 --> 00:00:01.000 align:start position:0%
            [music]

            00:00:01.000 --> 00:00:02.000 align:start position:0%
            >> Hi,<00:00:01.200><c> my</c><00:00:01.300><c> name</c><00:00:01.400><c> is</c><00:00:01.500><c> Mario.</c><00:00:01.600><c> I</c><00:00:01.700><c> hail</c><00:00:01.800><c> from</c><00:00:01.900><c> the</c>

            00:00:02.000 --> 00:00:03.000 align:start position:0%
            >> Hi, my name is Mario. I hail from the
            land<00:00:02.400><c> of</c><00:00:02.500><c> Arnold</c><00:00:02.600><c> Schwarzenegger,</c>

            00:00:03.000 --> 00:00:04.000 align:start position:0%
            land of Arnold Schwarzenegger,

            00:00:04.000 --> 00:00:05.000 align:start position:0%
            probably<00:00:04.100><c> haven't</c><00:00:04.200><c> noticed</c><00:00:04.300><c> yet.</c>
            """
        )

        cleaned = clean_vtt_text(vtt_text)

        self.assertEqual(
            cleaned,
            "Hi, my name is Mario. I hail from the land of Arnold Schwarzenegger, probably haven't noticed yet.",
        )

    def test_drops_bracketed_cues_and_leading_fillers(self) -> None:
        vtt_text = textwrap.dedent(
            """\
            WEBVTT

            00:00:00.000 --> 00:00:01.000
            >> [laughter]

            00:00:01.000 --> 00:00:02.000
            Um,<00:00:01.100><c> This</c><00:00:01.200><c> is</c><00:00:01.300><c> a</c><00:00:01.400><c> test</c><00:00:01.500><c>.</c>

            00:00:02.000 --> 00:00:03.000
            This is a test.

            00:00:03.000 --> 00:00:04.000
            I said oh<00:00:03.100><c> [&nbsp;__&nbsp;]</c><00:00:03.200><c> wow.</c>
            """
        )

        cleaned = clean_vtt_text(vtt_text)

        self.assertEqual(cleaned, "This is a test. I said oh wow.")

    def test_removes_embedded_speaker_markers(self) -> None:
        vtt_text = textwrap.dedent(
            """\
            WEBVTT

            00:00:00.000 --> 00:00:01.000
            Hello there. >>

            00:00:01.000 --> 00:00:02.000
            >> This<00:00:01.100><c> still</c><00:00:01.200><c> works.</c>
            """
        )

        cleaned = clean_vtt_text(vtt_text)

        self.assertEqual(cleaned, "Hello there. This still works.")
