"""
Main script demonstrating the Custom Story Video Generator workflow
"""

import os
import sys
from story_loader import load_stories_from_folder
from vidmaker import process_custom_story
from config import PATHS
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """Main function to demonstrate the workflow"""
    print("=" * 60)
    print("Custom Story Video Generator")
    print("Create YouTube Shorts by overlaying text on your videos")
    print("=" * 60)

    # Load stories from the stories folder
    print(f"\nLoading stories from '{PATHS['stories_folder']}' folder...")
    stories = load_stories_from_folder(PATHS["stories_folder"])

    if not stories:
        print(f"\nNo stories found in '{PATHS['stories_folder']}' folder!")
        print(f"Please add .txt story files to the '{PATHS['stories_folder']}' folder.")
        print("Each story file should have this format:")
        print("  Title: [Your Story Title]")
        print("  ")
        print("  [Your story text here]")
        print("  ")
        print("\nRunning in DEMO mode with sample story...\n")

        # Demo mode with sample story
        from vidmaker import create_custom_story_video
        from story_processor import process_story_text

        sample_story = """
        I never thought I'd see the day where my cat would outsmart me.

        It started three weeks ago when I noticed my sandwich kept disappearing
        from the kitchen counter. I blamed my roommate at first, but he swore
        he wasn't touching my food.

        So I set up a cheap webcam to see what was really happening.

        What I discovered changed everything: my tabby cat, Mr. Whiskers,
        had learned how to open the cabinet door, get out the bread,
        make himself a sandwich, and even clean up afterward!

        The most impressive part? He always uses exactly two slices of bread,
        adds mayo and turkey, and cuts it diagonally - just like I taught him
        to do when he was a kitten watching me make lunch.

        Now he makes me breakfast every morning. I guess you could say
        I'm no longer the head of this household.
        """

        print("Processing sample story...")
        processed_text = process_story_text(sample_story)
        print(f"   Original length: {len(sample_story)} characters")
        print(f"   Processed length: {len(processed_text)} characters")

        output_file = os.path.join(PATHS["output_folder"], "demo_story.mp4")
        print("Creating video: " + output_file)

        try:
            create_custom_story_video(processed_text, output_file, "Cat Makes Sandwiches")
            print(f"\nSuccess! Video created: {output_file}")
            print("\nTo use with your own stories:")
            print(f"   1. Add .txt story files to the '{PATHS['stories_folder']}' folder")
            print(f"   2. Add your videos (Subway Surfers, cooking, etc.) to the '{PATHS['input_videos_folder']}' folder")
            print(f"   3. Run this script again")
            print(f"   4. Videos will be generated from your stories and videos")
        except Exception as e:
            print(f"\nError creating video: {e}")
            logger.exception("Video creation failed")

        return

    # Process stories with available videos
    print(f"\nFound {len(stories)} stories to process")

    # Check for input videos
    from vidmaker import get_input_videos
    input_videos = get_input_videos()

    if not input_videos:
        print(f"\nNo input videos found in '{PATHS['input_videos_folder']}' folder!")
        print(f"Please add videos (Subway Surfers gameplay, cooking videos, etc.) to the '{PATHS['input_videos_folder']}' folder.")
        print("Supported formats: .mp4, .avi, .mov, .mkv, .webm, .flv")
        print("\nFor now, creating videos with solid color background...")

    # Process each story
    print(f"\nGenerating videos for {len(stories)} stories...")
    successful = 0

    for i, story in enumerate(stories, 1):
        print(f"\n[{i}/{len(stories)}] Processing: {story.title[:50]}...")
        print(f"    Words: {story.word_count} | File: {story.file_name}")

        try:
            video_path = process_custom_story(story)
            print(f"    [SUCCESS] Video created: {os.path.basename(video_path)}")
            successful += 1
        except Exception as e:
            print(f"    [ERROR] Failed to create video: {e}")
            logger.exception(f"Failed to process story {story.file_name}")

    print(f"\n{'='*60}")
    print(f"[SUCCESS] Workflow Complete! {successful}/{len(stories)} videos generated successfully")
    print(f"[INFO] Output directory: {os.path.abspath(PATHS['output_folder'])}")
    if input_videos:
        print(f"[INFO] Used videos from: {os.path.abspath(PATHS['input_videos_folder'])}")
    else:
        print(f"[WARNING] No input videos found - used solid color background")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()