import streamlit as st
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import pandas as pd
import re
import time
from collections import deque

# --- Core Logic ---

USER_AGENT = "WhatsAppLinkExtractor/1.0 (StreamlitApp; +https://github.com/yourusername/whatsapp-link-extractor)" # Be a good bot citizen
REQUEST_DELAY = 1 # Seconds between requests to be polite

def is_valid_url(url):
    """Checks if the URL is valid and has a scheme."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def get_domain(url):
    """Extracts the domain from a URL."""
    try:
        return urlparse(url).netloc
    except Exception:
        return None

def find_whatsapp_links(page_content):
    """Extracts WhatsApp group links from HTML content using regex."""
    # Regex for https://chat.whatsapp.com/INVITE_CODE
    # Invite codes are typically alphanumeric, can include hyphens or underscores.
    # Let's be a bit generous with the character set for the invite code.
    pattern = r"https?://chat\.whatsapp\.com/([A-Za-z0-9\-_]+)"
    return set(re.findall(pattern, page_content)) # Use set to store unique links

def crawl_website(start_url, max_depth, progress_bar, status_text):
    """
    Crawls a website starting from start_url up to max_depth,
    extracting WhatsApp group links.
    """
    if not is_valid_url(start_url):
        status_text.error(f"Invalid starting URL: {start_url}")
        return set(), 0

    start_domain = get_domain(start_url)
    if not start_domain:
        status_text.error(f"Could not determine domain for URL: {start_url}")
        return set(), 0

    # Queue stores (url, current_depth)
    queue = deque([(start_url, 0)])
    visited_urls = set()
    found_whatsapp_links = set()
    pages_crawled = 0

    headers = {'User-Agent': USER_AGENT}

    processed_urls_in_session = 0 # For progress bar estimate

    while queue:
        current_url, current_depth = queue.popleft()

        if current_url in visited_urls or current_depth > max_depth:
            continue

        visited_urls.add(current_url)
        status_text.info(f"Crawling (Depth {current_depth}): {current_url}")
        pages_crawled += 1
        processed_urls_in_session +=1

        # Update progress bar (estimate, as total pages unknown)
        # This is a simple progress, you might want something more sophisticated
        # if you have an estimate of total pages (which is hard without full crawl first)
        if processed_urls_in_session % 5 == 0 or len(queue) == 0 : # Update progress less frequently
             progress_bar.progress(min(1.0, processed_urls_in_session / (processed_urls_in_session + len(queue) +1e-6) ))


        try:
            time.sleep(REQUEST_DELAY) # Be polite
            response = requests.get(current_url, headers=headers, timeout=10)
            response.raise_for_status() # Raise HTTPError for bad responses (4XX or 5XX)

            # Ensure content type is HTML before parsing
            content_type = response.headers.get('content-type', '').lower()
            if 'text/html' not in content_type:
                status_text.warning(f"Skipping non-HTML content at {current_url} (type: {content_type})")
                continue

            soup = BeautifulSoup(response.text, 'html.parser')

            # 1. Extract WhatsApp links from the current page
            page_whatsapp_links = find_whatsapp_links(response.text)
            for link in page_whatsapp_links:
                full_link = f"https://chat.whatsapp.com/{link}" # Reconstruct full link
                found_whatsapp_links.add(full_link)

            # 2. Find new links to crawl (if within depth and domain)
            if current_depth < max_depth:
                for link_tag in soup.find_all('a', href=True):
                    href = link_tag['href']
                    absolute_link = urljoin(current_url, href) # Handles relative URLs

                    # Clean up the link (remove fragment, etc.)
                    parsed_link = urlparse(absolute_link)
                    clean_link = parsed_link._replace(fragment="", query="").geturl()


                    if is_valid_url(clean_link) and get_domain(clean_link) == start_domain and clean_link not in visited_urls:
                        queue.append((clean_link, current_depth + 1))

        except requests.exceptions.RequestException as e:
            status_text.warning(f"Failed to fetch {current_url}: {e}")
        except Exception as e:
            status_text.warning(f"Error processing {current_url}: {e}")

    progress_bar.progress(1.0) # Ensure progress bar completes
    return found_whatsapp_links, pages_crawled

# --- Streamlit App UI ---
st.set_page_config(page_title="WhatsApp Link Extractor", layout="wide")
st.title("🔗 WhatsApp Group Link Extractor")
st.markdown("""
This app scans a website by crawling pages within the same domain to extract WhatsApp group join links.
Adjust crawling depth, view progress, and download the results as a CSV file.
""")

# Input fields
start_url_input = st.text_input(
    "Enter Starting URL:",
    placeholder="e.g., https://example.com"
)
depth_input = st.slider(
    "Set Crawling Depth (0 for only the start page):",
    min_value=0, max_value=5, value=1, # Sensible max to prevent very long crawls
    help="How many 'clicks' deep to crawl from the starting URL. Higher values can take significantly longer."
)

if 'crawling_done' not in st.session_state:
    st.session_state.crawling_done = False
if 'found_links' not in st.session_state:
    st.session_state.found_links = []
if 'pages_crawled_count' not in st.session_state:
    st.session_state.pages_crawled_count = 0

# Crawl button
if st.button("🚀 Start Crawling", type="primary"):
    st.session_state.crawling_done = False
    st.session_state.found_links = []
    st.session_state.pages_crawled_count = 0

    if not start_url_input:
        st.error("⚠️ Please enter a starting URL.")
    elif not is_valid_url(start_url_input):
        st.error("⚠️ Please enter a valid URL (e.g., http:// or https://).")
    else:
        progress_bar_placeholder = st.empty()
        status_text_placeholder = st.empty()

        with st.spinner("🔍 Crawling in progress... Please wait."):
            progress_bar = progress_bar_placeholder.progress(0)
            found_links_set, pages_crawled = crawl_website(
                start_url_input,
                depth_input,
                progress_bar,
                status_text_placeholder
            )
        st.session_state.found_links = sorted(list(found_links_set))
        st.session_state.pages_crawled_count = pages_crawled
        st.session_state.crawling_done = True

        if st.session_state.found_links:
            status_text_placeholder.success(f"✅ Crawling complete! Found {len(st.session_state.found_links)} WhatsApp links across {st.session_state.pages_crawled_count} pages.")
        else:
            status_text_placeholder.info(f"ℹ️ Crawling complete. No WhatsApp links found after checking {st.session_state.pages_crawled_count} pages.")
        progress_bar_placeholder.empty() # Clear progress bar area


# Display results
if st.session_state.crawling_done:
    st.subheader(f"📊 Results: {len(st.session_state.found_links)} links found from {st.session_state.pages_crawled_count} pages")

    if st.session_state.found_links:
        df_links = pd.DataFrame(st.session_state.found_links, columns=["WhatsApp Group Link"])
        st.dataframe(df_links, use_container_width=True)

        # CSV Export
        csv_data = df_links.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Links as CSV",
            data=csv_data,
            file_name=f"whatsapp_links_{get_domain(start_url_input) or 'extracted'}.csv",
            mime='text/csv',
        )
    else:
        st.info("No WhatsApp group links were found on the crawled pages.")

st.markdown("---")
st.markdown("Built with [Streamlit](https://streamlit.io) by a helpful AI. "
            "Remember to respect website terms of service and robots.txt when crawling.")
