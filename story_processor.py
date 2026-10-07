"""
Text processing utilities for cleaning and preparing custom stories for TTS
"""

import re
import html
from typing import List
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StoryProcessor:
    """Processes custom stories for optimal TTS output"""

    def __init__(self):
        """Initialize the story processor"""
        # Compile regex patterns for efficiency
        self.markdown_patterns = [
            (r'\*\*(.*?)\*\*', r'\1'),      # Bold
            (r'\*(.*?)\*', r'\1'),          # Italic
            (r'~~(.*?)~~', r'\1'),          # Strikethrough
            (r'`(.*?)`', r'\1'),            # Inline code
            (r'```.*?```', ''),             # Code blocks (remove entirely)
            (r'^\s*>\s?', ''),              # Quote markers (handle per line)
            (r'^\s*[-*+]\s+', ''),          # List markers
            (r'^\s*\d+\.\s+', ''),          # Numbered list markers
        ]
        self.markdown_regex = [(re.compile(pattern, re.MULTILINE | re.DOTALL), replacement)
                              for pattern, replacement in self.markdown_patterns]

        # Whitespace cleanup
        self.whitespace_regex = re.compile(r'\s+')

        # Sentence splitting for better TTS pacing
        self.sentence_regex = re.compile(r'[.!?]+')

    def clean_markdown(self, text: str) -> str:
        """
        Remove markdown formatting

        Args:
            text: Raw text with markdown

        Returns:
            Cleaned text without markdown
        """
        if not text:
            return ""

        # Handle blockquotes first (multiline)
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            # Remove quote markers
            line = re.sub(r'^\s*>\s?', '', line)
            cleaned_lines.append(line)
        text = '\n'.join(cleaned_lines)

        # Apply other markdown patterns
        for pattern, replacement in self.markdown_regex:
            text = pattern.sub(replacement, text)

        return text

    def clean_whitespace(self, text: str) -> str:
        """
        Clean up excessive whitespace and newlines

        Args:
            text: Text to clean

        Returns:
            Text with normalized whitespace
        """
        if not text:
            return ""

        # Replace multiple newlines with single newline
        text = re.sub(r'\n\s*\n', '\n\n', text)
        # Replace multiple spaces with single space
        text = self.whitespace_regex.sub(' ', text)
        # Strip leading/trailing whitespace
        text = text.strip()

        return text

    def fix_punctuation(self, text: str) -> str:
        """
        Fix and normalize punctuation for better TTS flow

        Args:
            text: Text to fix

        Returns:
            Text with improved punctuation
        """
        if not text:
            return ""

        # Fix spacing around punctuation
        text = re.sub(r'\s+([,.!?;:])', r'\1', text)  # Remove space before punctuation
        text = re.sub(r'([,.!?;:])\s*', r'\1 ', text)  # Ensure single space after

        # Fix multiple punctuation marks
        text = re.sub(r'[.]{2,}', '...', text)        # Multiple periods to ellipsis
        text = re.sub(r'[!]{2,}', '!!', text)         # Multiple exclamations
        text = re.sub(r'[?]{2,}', '??', text)         # Multiple questions

        # Fix quotes
        text = re.sub(r'"([^"]*)"', r'"\1"', text)    # Normalize quotes
        text = re.sub(r"'([^']*)'", r"'\1'", text)    # Normalize apostrophes

        return text.strip()

    def process_story(self, raw_text: str) -> str:
        """
        Apply all processing steps to raw story text

        Args:
            raw_text: Raw text from story

        Returns:
            Processed text optimized for TTS
        """
        if not raw_text:
            return ""

        logger.debug(f"Processing story text of length {len(raw_text)}")

        # Step 1: HTML decode (in case of HTML entities)
        text = html.unescape(raw_text)

        # Step 2: Clean markdown formatting
        text = self.clean_markdown(text)

        # Step 3: Fix punctuation
        text = self.fix_punctuation(text)

        # Step 4: Clean whitespace
        text = self.clean_whitespace(text)

        logger.debug(f"Processed story text to length {len(text)}")
        return text

    def split_into_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences for better TTS timing control

        Args:
            text: Processed text

        Returns:
            List of sentences
        """
        if not text:
            return []

        # Split on sentence endings but keep the punctuation
        sentences = self.sentence_regex.split(text)
        # Filter out empty strings
        sentences = [s.strip() for s in sentences if s.strip()]

        return sentences

    def estimate_speech_duration(self, text: str, words_per_second: float = 2.5) -> float:
        """
        Estimate how long the text will take to speak

        Args:
            text: Text to estimate
            words_per_second: Average speaking rate

        Returns:
            Estimated duration in seconds
        """
        if not text:
            return 0.0

        word_count = len(text.split())
        duration = word_count / words_per_second
        return duration

# Convenience functions for easy import
def process_story_text(raw_text: str) -> str:
    """
    Convenience function to process a story text

    Args:
        raw_text: Raw story text

    Returns:
        Processed text ready for TTS
    """
    processor = StoryProcessor()
    return processor.process_story(raw_text)

def estimate_duration(text: str, wps: float = 2.5) -> float:
    """
    Convenience function to estimate speech duration

    Args:
        text: Processed text
        wps: Words per second

    Returns:
        Estimated duration in seconds
    """
    processor = StoryProcessor()
    return processor.estimate_speech_duration(text, wps)

# Example usage and testing
if __name__ == "__main__":
    # Test with sample text
    sample_text = """
    This is a test story for the Custom Story Video Generator.

    It has multiple paragraphs and some formatting.

    Let's see how well the text processing works!
    """

    processor = StoryProcessor()
    processed = processor.process_story(sample_text)

    print("Original text:")
    print(repr(sample_text))
    print("\nProcessed text:")
    print(repr(processed))
    print(f"\nEstimated duration: {processor.estimate_speech_duration(processed):.1f} seconds")
    print(f"Word count: {len(processed.split())} words")