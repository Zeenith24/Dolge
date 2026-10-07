"""
Story loader for loading custom stories from text files
"""

import os
from typing import List, Optional
from dataclasses import dataclass
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class CustomStory:
    """Data class to hold custom story information"""
    title: str
    text: str
    file_name: str

    @property
    def full_text(self) -> str:
        """Get the full text"""
        return self.text

    @property
    def word_count(self) -> int:
        """Get approximate word count"""
        return len(self.text.split())

class StoryLoader:
    """Loads stories from text files in the stories folder"""

    def __init__(self, stories_folder: str = "stories"):
        """
        Initialize the story loader

        Args:
            stories_folder: Folder containing story .txt files
        """
        self.stories_folder = stories_folder
        # Ensure the folder exists
        os.makedirs(self.stories_folder, exist_ok=True)

    def load_stories(self) -> List[CustomStory]:
        """
        Load all stories from the stories folder

        Returns:
            List of CustomStory objects
        """
        stories = []

        if not os.path.exists(self.stories_folder):
            logger.warning(f"Stories folder '{self.stories_folder}' does not exist")
            return stories

        # Get all supported story files
        story_files = []
        for filename in os.listdir(self.stories_folder):
            if any(filename.endswith(ext) for ext in ['.txt']):
                story_files.append(os.path.join(self.stories_folder, filename))

        logger.info(f"Found {len(story_files)} story files in '{self.stories_folder}'")

        for file_path in story_files:
            try:
                story = self._load_story_from_file(file_path)
                if story:
                    stories.append(story)
                    logger.info(f"Loaded story: {story.title} ({story.word_count} words)")
            except Exception as e:
                logger.error(f"Error loading story from {file_path}: {e}")
                continue

        logger.info(f"Successfully loaded {len(stories)} stories")
        return stories

    def _load_story_from_file(self, file_path: str) -> Optional[CustomStory]:
        """
        Load a single story from a text file

        Expected format:
        Title: [Story Title]

        [Story text]
        Can be multiple paragraphs

        Args:
            file_path: Path to the story file

        Returns:
            CustomStory object or None if invalid
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()

            if not content:
                logger.warning(f"Story file is empty: {file_path}")
                return None

            # Parse title and text
            lines = content.split('\n')
            title = "Untitled Story"
            text_lines = []

            # Look for title line
            title_found = False
            for i, line in enumerate(lines):
                line = line.strip()
                if line.startswith("Title:"):
                    title = line[6:].strip()  # Remove "Title:" prefix
                    title_found = True
                    # Text starts after the title line
                    text_lines = lines[i+1:]
                    break

            # If no title found, use filename as title and all content as text
            if not title_found:
                title = os.path.splitext(os.path.basename(file_path))[0]
                text_lines = lines

            # Join text lines and clean up
            text = '\n'.join(text_lines).strip()

            # Remove extra blank lines at start and end
            text = text.strip()

            if not text:
                logger.warning(f"No text content found in story file: {file_path}")
                return None

            return CustomStory(
                title=title,
                text=text,
                file_name=os.path.basename(file_path)
            )

        except Exception as e:
            logger.error(f"Error reading story file {file_path}: {e}")
            return None

    def get_story_count(self) -> int:
        """
        Get the number of available stories

        Returns:
            Number of story files
        """
        if not os.path.exists(self.stories_folder):
            return 0

        count = 0
        for filename in os.listdir(self.stories_folder):
            if any(filename.endswith(ext) for ext in ['.txt']):
                count += 1

        return count

# Convenience function
def load_stories_from_folder(folder_path: str = "stories") -> List[CustomStory]:
    """
    Convenience function to load stories from a folder

    Args:
        folder_path: Path to stories folder

    Returns:
        List of CustomStory objects
    """
    loader = StoryLoader(folder_path)
    return loader.load_stories()

# Example usage and testing
if __name__ == "__main__":
    loader = StoryLoader()
    stories = loader.load_stories()

    print(f"Loaded {len(stories)} stories:")
    for i, story in enumerate(stories, 1):
        print(f"\n{i}. {story.title}")
        print(f"   File: {story.file_name}")
        print(f"   Words: {story.word_count}")
        print(f"   Preview: {story.text[:100]}...")