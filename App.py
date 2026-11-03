import re
from urllib.parse import urlparse

COURT_SOURCES = {
    "Supreme Court of India": {
        "allowed_hosts": ("sci.gov.in", "judgments.ecourts.gov.in"),
        "search_url": "https://www.sci.gov.in/free-text-judgements/",
    },
    "Calcutta High Court": {
        "allowed_hosts": (
            "calcuttahighcourt.gov.in",
            "judgments.ecourts.gov.in",
        ),
        "search_url": "https://www.calcuttahighcourt.gov.in/",
    },
}

ESCR_SEARCH_URL = (
    "https://judgments.ecourts.gov.in/pdfsearch/"
    "?p=pdf_search%2Findex&escr_flag=Y#?app_token="
)


def is_official_source_url(url, court):
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username:
        return False

    hostname = parsed.hostname.lower().rstrip(".")
    return any(
        hostname == allowed_host or hostname.endswith(f".{allowed_host}")
        for allowed_host in COURT_SOURCES[court]["allowed_hosts"]
    )

try:
    import streamlit as st
except ModuleNotFoundError as exc:
    if exc.name == "streamlit":
        raise SystemExit(
            "Streamlit is not installed. Run: python -m pip install streamlit"
        ) from exc
    raise


def read_judgment(uploaded_file):
    filename = uploaded_file.name.lower()

    if filename.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ModuleNotFoundError:
            return None, "PDF support needs pypdf. Run: python -m pip install pypdf"

        reader = PdfReader(uploaded_file)
        pages = [
            {"number": page_number, "text": page.extract_text() or ""}
            for page_number, page in enumerate(reader.pages, start=1)
        ]
    elif filename.endswith(".txt"):
        text = uploaded_file.getvalue().decode("utf-8", errors="replace")
        pages = [{"number": None, "text": text}]
    else:
        return None, "Upload a PDF or UTF-8 text file."

    if not any(page["text"].strip() for page in pages):
        return None, "No selectable text was found. Scanned PDFs need OCR first."

    return pages, None


def citation_pattern(citation):
    parts = citation.split()
    return re.compile(r"\s+".join(re.escape(part) for part in parts), re.IGNORECASE)


def evidence_snippet(text, start, end, radius=110):
    excerpt_start = max(0, start - radius)
    excerpt_end = min(len(text), end + radius)
    prefix = "..." if excerpt_start else ""
    suffix = "..." if excerpt_end < len(text) else ""
    excerpt = text[excerpt_start:excerpt_end].replace("\n", " ")
    return f"{prefix}{excerpt}{suffix}"


def find_citation_mentions(cases):
    mentions = []
    for source in cases:
        for target in cases:
            if source["citation"].casefold() == target["citation"].casefold():
                continue

            pattern = citation_pattern(target["citation"])
            for page in source["pages"]:
                for match in pattern.finditer(page["text"]):
                    mentions.append(
                        {
                            "source": source["title"],
                            "target": target["title"],
                            "source_court": source.get("court", "Court not recorded"),
                            "target_court": target.get("court", "Court not recorded"),
                            "citation": target["citation"],
                            "page": page["number"],
                            "evidence": evidence_snippet(
                                page["text"], match.start(), match.end()
                            ),
                        }
                    )
    return mentions


st.set_page_config(page_title="LEXISCOPE", page_icon="⚖️", layout="wide")

if "cases" not in st.session_state:
    st.session_state.cases = []

st.title("LEXISCOPE")
st.subheader("Judgment research workspace")
st.write("Step 1: build a case library and inspect citation links in your documents.")
st.subheader("Step 2: find judgments on official portals")
st.write(
    "Search the court portal yourself, complete its CAPTCHA, and download the judgment. "
    "Then add the PDF below. This app does not bypass portal controls or fetch cases in bulk."
)
st.link_button(
    "Supreme Court free-text judgment search",
    COURT_SOURCES["Supreme Court of India"]["search_url"],
)
st.link_button("eSCR search (select the court)", ESCR_SEARCH_URL)
st.link_button(
    "Calcutta High Court official site",
    COURT_SOURCES["Calcutta High Court"]["search_url"],
)
st.link_button(
    "Calcutta High Court neutral-citation lookup",
    "https://www.calcuttahighcourt.gov.in/Find-Neutral-Citation-No-Using-Case-No",
)

with st.sidebar.form("add_judgment", clear_on_submit=True):
    st.subheader("Add a judgment")
    court = st.selectbox("Court", list(COURT_SOURCES))
    source_type = st.selectbox(
        "Document source", ["User-provided file", "Official court download"]
    )
    title = st.text_input("Case title")
    citation = st.text_input("Full reported or neutral citation")
    official_url = st.text_input("Official judgment page or PDF URL")
    uploaded_file = st.file_uploader("Judgment file", type=["pdf", "txt"])
    add_judgment = st.form_submit_button("Add to this session")

if add_judgment:
    if court not in COURT_SOURCES:
        st.sidebar.error("Choose a supported court.")
    elif source_type not in ["User-provided file", "Official court download"]:
        st.sidebar.error("Choose a supported document source.")
    elif not title.strip() or not citation.strip() or uploaded_file is None:
        st.sidebar.error("Enter the case title and citation, then select a file.")
    elif source_type == "Official court download" and not is_official_source_url(
        official_url, court
    ):
        st.sidebar.error(
            "Enter an HTTPS judgment URL on the selected court's official domain or eSCR."
        )
    elif any(
        case.get("court") == court
        and case["citation"].casefold() == citation.strip().casefold()
        for case in st.session_state.cases
    ):
        st.sidebar.error("That court and citation are already in this session's library.")
    else:
        pages, error = read_judgment(uploaded_file)
        if error:
            st.sidebar.error(error)
        else:
            st.session_state.cases.append(
                {
                    "title": title.strip(),
                    "citation": citation.strip(),
                    "court": court,
                    "source_type": source_type,
                    "official_url": official_url.strip()
                    if source_type == "Official court download"
                    else "",
                    "filename": uploaded_file.name,
                    "pages": pages,
                }
            )
            st.sidebar.success(f"Added {title.strip()} to this session.")

if st.sidebar.button("Clear session case library", disabled=not st.session_state.cases):
    st.session_state.cases = []

st.caption(
    "Only user-provided files are searched. Documents and extracted text stay in this app session. "
    "Official URLs are checked against supported domains, but the file is not independently authenticated."
)

if not st.session_state.cases:
    st.info("Add at least two judgments to find citations between cases in your library.")
else:
    st.metric("Judgments in this session", len(st.session_state.cases))

    query = st.text_input("Search words or a phrase in the uploaded judgments")
    if query.strip():
        query_pattern = re.compile(re.escape(query.strip()), re.IGNORECASE)
        matches_found = 0
        for case in st.session_state.cases:
            for page in case["pages"]:
                match = query_pattern.search(page["text"])
                if match:
                    matches_found += 1
                    page_label = f"Page {page['number']}" if page["number"] else "Text file"
                    with st.expander(f"{case['title']} - {page_label}"):
                        st.write(
                            evidence_snippet(
                                page["text"], match.start(), match.end(), 180
                            )
                        )
        if not matches_found:
            st.info("No exact text matches found in this session's documents.")

    st.subheader("Citation cross-references")
    mentions = find_citation_mentions(st.session_state.cases)
    if mentions:
        for mention in mentions:
            page_label = f"Page {mention['page']}" if mention["page"] else "Text file"
            st.markdown(
                f"**{mention['source']}** ({mention['source_court']}) cites "
                f"**{mention['target']}** ({mention['target_court']}) "
                f"({mention['citation']}) - {page_label}"
            )
            st.caption(mention["evidence"])
    else:
        st.info("No exact matches for the other cases' registered citations were found.")

    st.warning(
        "A citation match only shows that the text mentions a case. It does not establish "
        "whether the court followed, distinguished, questioned, or overruled it. "
        "Verify every passage against the original judgment."
    )

    with st.expander("Cases currently in this session"):
        for case in st.session_state.cases:
            st.write(
                f"{case['title']} - {case['citation']} "
                f"({case.get('court', 'Court not recorded')}; {case['filename']})"
            )
            st.caption(case.get("source_type", "User-provided file"))
            if case.get("official_url"):
                st.link_button("Open recorded source", case["official_url"])