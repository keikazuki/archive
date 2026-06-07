"""
DatabaseHandler.py
Handles all connections to the database. The database runs on PostgreSQL and is connected to via psycopg2.
"""

import psycopg2
import traceback
import logging
import time
from psycopg2.extras import execute_values

logger = logging.getLogger("archive")

MEDIA_INSERT_QUERY = """
INSERT INTO media(hash, submission_id, subreddit, frame_number, frame_count, frame_width, frame_height, total_pixels, file_size)
VALUES %s
ON CONFLICT DO NOTHING;
"""

SUBMISSION_INSERT_QUERY = """
INSERT INTO submissions(id, subreddit, timestamp, author, title, url, comments, score, deleted, processed)
VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (id) DO UPDATE SET
processed = COALESCE(submissions.processed, FALSE) OR COALESCE(EXCLUDED.processed, FALSE);
"""

DBNAME = ""
DBUSER = ""
DBPASSWORD = ""
DBHOST = ""
DBPORT = ""
conn = None
cur = None

try:
    import config

    DBNAME = config.DBNAME
    DBUSER = config.DBUSER
    DBPASSWORD = config.DBPASSWORD
    DBHOST = config.DBHOST
    DBPORT = config.DBPORT
except ImportError:
    pass


class ArchiveDatabaseError(Exception):
    pass


def connectDatabase():
    global conn, cur
    conn = psycopg2.connect(
        user=DBUSER, password=DBPASSWORD, host=DBHOST, port=DBPORT, dbname=DBNAME
    )
    conn.autocommit = True
    cur = conn.cursor()


def ensureDatabaseConnection():
    global cur
    if conn is None or conn.closed:
        connectDatabase()
    elif cur is None or cur.closed:
        cur = conn.cursor()


try:
    connectDatabase()
except Exception as e:
    print("DB Connection Failed. Error = {0}".format(e), flush=True)
    logger.warning("DB Connection Failed. Error = {0}".format(e))

"""
    Code for create tables
"""


def submissionExists(submissionid):
    """
    Returns true if the submission exists inside table.
    """
    query = "SELECT 1 FROM submissions WHERE id = %s LIMIT 1;"

    try:
        ensureDatabaseConnection()
        cur.execute(query, (submissionid,))
        exists = (cur.fetchone()) is not None
        logger.debug(f"\t [DB] Submission {submissionid} exists: {exists}")
        return exists
    except Exception as e:
        traceback.print_exc()
        logger.warning(f"\t [DB] Failed to check submission {submissionid}: {e}")
        raise ArchiveDatabaseError(f"Failed to check submission {submissionid}") from e


def getArchieveSubredditsList():
    """
    List of subreddits to index in background (reads posts and index images/gifs/videos) Will not comment for these subreddits
    """
    start_time = time.time()
    query = "SELECT subreddit FROM indexsubreddits;"

    try:
        ensureDatabaseConnection()
        sublist = []
        cur.execute(query)
        subredditslist = cur.fetchall()
        for item in subredditslist:
            if item[0]:
                sublist.append(str(item[0]))
        subreddit_list = "+".join(sublist)
        elapsed = time.time() - start_time
        logger.info(
            f"\t [DB] Loaded {len(sublist)} archive subreddit(s) in {elapsed:.3f}s"
        )
        return subreddit_list
    except Exception as e:
        traceback.print_exc()
        logger.warning(f"\t [DB] Failed to load archive subreddits: {e}")
        return


def getRepostCheckerList():
    """
    List of subreddits to index in background (reads posts and index images/gifs/videos) Will comment for these subreddits
    """
    start_time = time.time()
    query = "SELECT subreddit FROM checksubreddits;"

    try:
        ensureDatabaseConnection()
        sublist = []
        cur.execute(query)
        subredditslist = cur.fetchall()
        for item in subredditslist:
            if item[0]:
                sublist.append(str(item[0]))
        subreddit_list = "+".join(sublist)
        elapsed = time.time() - start_time
        logger.info(
            f"\t [DB] Loaded {len(sublist)} repostchecker subreddit(s) in {elapsed:.3f}s"
        )
        return subreddit_list
    except Exception as e:
        traceback.print_exc()
        logger.warning(f"\t [DB] Failed to load repostchecker subreddits: {e}")
        return


def addSubmission(submissionData):
    """
    Adds a submission record into Submissions Table.
    """
    submission_id = submissionData[0] if submissionData else "unknown"
    subreddit = (
        submissionData[1] if submissionData and len(submissionData) > 1 else "unknown"
    )

    try:
        ensureDatabaseConnection()
        cur.execute(SUBMISSION_INSERT_QUERY, submissionData)
        logger.debug(f"\t [DB] Added submission {submission_id} ({subreddit})")
    except Exception as e:
        traceback.print_exc()
        if conn is not None and not conn.closed:
            conn.rollback()
        logger.warning(f"\t [DB] Failed to add submission {submission_id}: {e}")


def addMedia(mediaData):
    """
    Adds a media record into Media Table.
    """
    submission_id = mediaData[1] if mediaData and len(mediaData) > 1 else "unknown"

    try:
        ensureDatabaseConnection()
        execute_values(cur, MEDIA_INSERT_QUERY, [mediaData], page_size=1)
        logger.debug(f"\t [DB] Added media hash for submission {submission_id}")
        return True
    except Exception as e:
        traceback.print_exc()
        if conn is not None and not conn.closed:
            conn.rollback()
        logger.warning(
            f"\t [DB] Failed to add media for submission {submission_id}: {e}"
        )
        return False


def addSubmissionAndMedia(submissionData, mediaRows):
    """
    Adds all media rows and the submission in one transaction.
    """
    start_time = time.time()
    mediaRows = [media for media in mediaRows if media is not None]
    submission_id = submissionData[0] if submissionData else "unknown"
    previous_autocommit = None

    try:
        ensureDatabaseConnection()
        previous_autocommit = conn.autocommit
        conn.autocommit = False

        if mediaRows:
            execute_values(cur, MEDIA_INSERT_QUERY, mediaRows, page_size=100)

        if submissionData is not None:
            cur.execute(SUBMISSION_INSERT_QUERY, submissionData)

        conn.commit()
        elapsed = time.time() - start_time
        logger.info(
            f"\t [DB] Committed submission {submission_id} with {len(mediaRows)} media row(s) in {elapsed:.3f}s"
        )
        return len(mediaRows) > 0
    except Exception as e:
        if conn is not None and not conn.closed:
            conn.rollback()
        traceback.print_exc()
        elapsed = time.time() - start_time
        logger.warning(
            f"\t [DB] Failed to commit submission {submission_id} after {elapsed:.3f}s: {e}"
        )
        return False
    finally:
        if previous_autocommit is not None and conn is not None and not conn.closed:
            conn.autocommit = previous_autocommit


def getAllMedia():
    """
    Returns hash, submission_id, subreddit of all records of media table.
    """
    query = "SELECT hash, submission_id, subreddit FROM media WHERE frame_count=1 and hash <> '9925021303884596990' and hash <> '18446744073709551615' and subreddit <> 'ssaavvaaggeekkuunn';"

    try:
        ensureDatabaseConnection()
        cur.execute(query)
        rows = cur.fetchall()
        logger.debug(f"\t [DB] Loaded {len(rows)} media row(s)")
        return rows
    except Exception as e:
        traceback.print_exc()
        logger.warning(f"\t [DB] Failed to load media rows: {e}")
        return


def getSubmission(submissionid):
    """
    Returns id, subreddit of all records.
    """
    query = (
        "SELECT id, subreddit, timestamp, author, title FROM submissions WHERE id = %s;"
    )

    try:
        ensureDatabaseConnection()
        cur.execute(query, (submissionid,))
        submission = cur.fetchone()
        logger.debug(
            f"\t [DB] Loaded submission {submissionid}: {submission is not None}"
        )
        return submission
    except Exception as e:
        traceback.print_exc()
        logger.warning(f"\t [DB] Failed to load submission {submissionid}: {e}")
        return


def commentExists(commentid):
    """
    Returns true if the comment exists inside mentions table.
    """
    query = "SELECT 1 FROM mentions WHERE commentid = %s LIMIT 1;"

    try:
        ensureDatabaseConnection()
        cur.execute(query, (commentid,))
        exists = (cur.fetchone()) is not None
        logger.debug(f"\t [DB] Comment {commentid} exists: {exists}")
        return exists
    except Exception as e:
        traceback.print_exc()
        logger.warning(f"\t [DB] Failed to check comment {commentid}: {e}")
        return True


def addComment(commentid, submission_id, type, requester, subreddit):
    """
    Add a record in mentions table.
    """
    query = "INSERT INTO mentions(commentid, submission_id, type, requester, subreddit) VALUES(%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING;"

    try:
        ensureDatabaseConnection()
        cur.execute(query, (commentid, submission_id, type, requester, subreddit))
        logger.debug(
            f"\t [DB] Added comment {commentid} for submission {submission_id}"
        )
    except Exception as e:
        traceback.print_exc()
        if conn is not None and not conn.closed:
            conn.rollback()
        logger.warning(f"\t [DB] Failed to add comment {commentid}: {e}")
