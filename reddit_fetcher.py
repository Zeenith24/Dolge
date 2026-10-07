"""
Reddit API fetcher for retrieving stories from specified subreddits
"""

import praw
import time
from typing import List, Dict, Optional
from dataclasses import dataclass
from config import REDDIT_CONFIG, TARGET_SUBREDDITS, REDDIT_SETTINGS
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class RedditStory:
    """Data class to hold Reddit story information"""
    title: str
    selftext: str
    score: int
    num_comments: int
    subreddit: str
    url: str
    created_utc: float
    id: str

    @property
    def full_text(self) -> str:
        """Get the full text combining title and selftext"""
        if self.selftext:
            return f"{self.title}. {self.selftext}"
        return self.title

    @property
    def word_count(self) -> int:
        """Get approximate word count"""
        return len(self.full_text.split())

class RedditFetcher:
    """Handles interaction with Reddit API to fetch stories"""

    def __init__(self):
        """Initialize Reddit API connection"""
        try:
            self.reddit = praw.Reddit(
                client_id=REDDIT_CONFIG["client_id"],
                client_secret=REDDIT_CONFIG["client_secret"],
                user_agent=REDDIT_CONFIG["user_agent"],
                check_for_async=False
            )
            # Test the connection
            self.reddit.user.me()
            logger.info("Successfully connected to Reddit API")
        except Exception as e:
            logger.error(f"Failed to connect to Reddit API: {e}")
            raise

    def fetch_stories(
        self,
        subreddits: Optional[List[str]] = None,
        limit: Optional[int] = None,
        time_filter: Optional[str] = None
    ) -> List[RedditStory]:
        """
        Fetch stories from specified subreddits

        Args:
            subreddits: List of subreddit names (defaults to TARGET_SUBREDDITS)
            limit: Number of posts to fetch per subreddit
            time_filter: Time filter for posts (hour, day, week, month, year, all)

        Returns:
            List of RedditStory objects
        """
        if subreddits is None:
            subreddits = TARGET_SUBREDDITS
        if limit is None:
            limit = REDDIT_SETTINGS["posts_per_subreddit"]
        if time_filter is None:
            time_filter = REDDIT_SETTINGS["time_filter"]

        stories = []

        for subreddit_name in subreddits:
            try:
                logger.info(f"Fetching stories from r/{subreddit_name}")
                subreddit = self.reddit.subreddit(subreddit_name)

                # Get posts from the subreddit
                posts = subreddit.top(
                    time_filter=time_filter,
                    limit=limit
                )

                for post in posts:
                    # Skip stickied posts if configured
                    if REDDIT_SETTINGS["exclude_stickied"] and post.stickied:
                        continue

                    # Skip NSFW posts if configured
                    if REDDIT_SETTINGS["exclude_nsfw"] and post.over_18:
                        continue

                    # Skip link posts (posts with URLs that aren't self posts)
                    if post.is_self is False:
                        continue

                    # Check post length
                    full_text = f"{post.title}. {post.selftext}" if post.selftext else post.title
                    if len(full_text) > REDDIT_SETTINGS["max_post_length"]:
                        logger.debug(f"Skipping post {post.id} - too long ({len(full_text)} chars)")
                        continue

                    # Check minimum score
                    if post.score < REDDIT_SETTINGS["min_score"]:
                        logger.debug(f"Skipping post {post.id} - score too low ({post.score})")
                        continue

                    # Create RedditStory object
                    story = RedditStory(
                        title=post.title,
                        selftext=post.selftext,
                        score=post.score,
                        num_comments=post.num_comments,
                        subreddit=subreddit_name,
                        url=post.url,
                        created_utc=post.created_utc,
                        id=post.id
                    )

                    stories.append(story)
                    logger.debug(f"Fetched story: {story.title[:50]}... (Score: {story.score})")

                # Rate limiting - be respectful to Reddit's API
                time.sleep(1)

            except Exception as e:
                logger.error(f"Error fetching from r/{subreddit_name}: {e}")
                continue

        logger.info(f"Fetched {len(stories)} stories total")
        return stories

    def fetch_story_by_id(self, story_id: str) -> Optional[RedditStory]:
        """
        Fetch a specific story by its ID

        Args:
            story_id: Reddit post ID

        Returns:
            RedditStory object or None if not found/error
        """
        try:
            submission = self.reddit.submission(id=story_id)
            story = RedditStory(
                title=submission.title,
                selftext=submission.selftext,
                score=submission.score,
                num_comments=submission.num_comments,
                subreddit=submission.subreddit.display_name,
                url=submission.url,
                created_utc=submission.created_utc,
                id=submission.id
            )
            return story
        except Exception as e:
            logger.error(f"Error fetching story {story_id}: {e}")
            return None

    def get_trending_stories(self, limit: int = 10) -> List[RedditStory]:
        """
        Get trending stories across all target subreddits

        Args:
            limit: Maximum number of stories to return

        Returns:
            List of top RedditStory objects sorted by score
        """
        stories = self.fetch_stories(limit=None)  # Fetch all available
        # Sort by score descending and return top stories
        trending = sorted(stories, key=lambda x: x.score, reverse=True)[:limit]
        return trending

# Example usage and testing
if __name__ == "__main__":
    fetcher = RedditFetcher()
    stories = fetcher.fetch_stories(limit=5)

    print(f"Fetched {len(stories)} stories:")
    for i, story in enumerate(stories, 1):
        print(f"\n{i}. r/{story.subreddit} - {story.title}")
        print(f"   Score: {story.score} | Comments: {story.num_comments}")
        print(f"   Preview: {story.full_text[:100]}...")