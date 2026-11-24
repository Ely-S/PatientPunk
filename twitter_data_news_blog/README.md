# Spikes and Steps

Open [the blog post](post.html) or [the presentation](slides.html) in a browser after cloning the branch. Both are ready to read offline. Edit [post.md](post.md) for the article and [slides.html](slides.html) for the deck. The article renderer embeds the [SVG figures](figures/) in the HTML.

## Reproduce the analysis

From the repository root, use Python 3 and MinIO Client (`mc`) with an alias that has read access to the private PatientPunk bucket. Allow about 1.1 GB for the research inputs. Substitute your configured alias below.

```sh
python3 twitter_data_news_blog/download_data.py --alias patientpunk-s3
python3 twitter_data_news_blog/analysis/extract.py
uv run --with numpy --with pandas --with matplotlib --with scipy python twitter_data_news_blog/analysis/analyze.py
uv run --with numpy --with markdown python twitter_data_news_blog/analysis/render.py
```

The downloader checks each input against [the SHA-256 manifest](data-files.sha256) and skips matching local copies on subsequent runs. Extraction recreates the private per-post CSVs. Analysis updates aggregate tables and figures, and rendering refreshes the article. The presentation is edited directly. Raw inputs, including research notes with account-level examples, belong in private storage.
