# Core packages
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

import neattext.functions as nfx
import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as stc


# Page settings
st.set_page_config(
    page_title="Contact Extractor",
    page_icon="📇",
    layout="wide",
)

# Keep the existing database filename to retain saved data.
DB_PATH = Path(__file__).resolve().parent / "emails_data.db"

TASKS = ["Emails", "URLs", "Phone numbers"]

EXTRACTORS = {
    "Emails": nfx.extract_emails,
    "URLs": nfx.extract_urls,
    "Phone numbers": nfx.extract_phone_numbers,
}

DATABASE_FIELDS = {
    "Emails": ("extracted_emails", "email", "Email"),
    "URLs": ("extracted_urls", "url", "URL"),
    "Phone numbers": ("extracted_phones", "phone_number", "Phone_number"),
}

DISPLAY_NAMES = {
    "Emails": "emails",
    "URLs": "URLs",
    "Phone numbers": "phone numbers",
}


# --------------------------------------------------
# Database functions
# --------------------------------------------------
def initialise_database():
    """Create tables for emails, URLs, and phone numbers."""
    with closing(sqlite3.connect(DB_PATH, timeout=15)) as conn:
        with conn:
            # Table and column names come from this fixed mapping.
            for table, column, _ in DATABASE_FIELDS.values():
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {table} (
                        {column} TEXT PRIMARY KEY,
                        saved_at TEXT NOT NULL
                    )
                    """
                )


def save_records(values, task):
    """Save unique values and return the number added."""
    table, column, _ = DATABASE_FIELDS[task]

    cleaned = sorted({
        str(value).strip()
        for value in values
        if pd.notna(value) and str(value).strip()
    })

    if not cleaned:
        return 0

    saved_at = datetime.now().isoformat(timespec="seconds")

    with closing(sqlite3.connect(DB_PATH, timeout=15)) as conn:
        with conn:
            before = conn.total_changes

            conn.executemany(
                f"""
                INSERT OR IGNORE INTO {table} ({column}, saved_at)
                VALUES (?, ?)
                """,
                [(value, saved_at) for value in cleaned],
            )

            return conn.total_changes - before


def load_records(task):
    """Read saved values using a fresh connection."""
    table, column, display_column = DATABASE_FIELDS[task]

    with closing(sqlite3.connect(DB_PATH, timeout=15)) as conn:
        return pd.read_sql_query(
            f"""
            SELECT {column} AS {display_column}, saved_at AS Saved_at
            FROM {table}
            ORDER BY saved_at DESC, {column}
            """,
            conn,
        )


# --------------------------------------------------
# Extraction and download functions
# --------------------------------------------------
def extract_results(text, selected_tasks):
    """Extract unique results and align columns of different lengths."""
    columns = {}

    for task in selected_tasks:
        values = EXTRACTORS[task](text)

        # Remove duplicates while keeping their original order.
        unique_values = list(dict.fromkeys(values))

        columns[task] = pd.Series(unique_values, dtype="object")

    return pd.DataFrame(columns)


def show_results(result_df, key):
    """Display, download, and save selected extracted data."""
    if result_df.empty:
        st.info("No matching results were found.")
        return

    available_tasks = [
        task for task in TASKS
        if task in result_df.columns
        and result_df[task].notna().any()
    ]

    selected_types = st.multiselect(
        "Select data to display, download, or save",
        options=available_tasks,
        default=available_tasks,
        key=f"result_types_{key}",
    )

    if not selected_types:
        st.info("Select at least one data type.")
        return

    selected_df = (
        result_df[selected_types]
        .dropna(how="all")
        .reset_index(drop=True)
    )

    for task in selected_types:
        count = selected_df[task].notna().sum()
        st.write(f"**{task}:** {count}")

    with st.expander("Results Table", expanded=True):
        st.dataframe(selected_df)

    st.caption(
        "Each column is an independent list. "
        "Items on the same row are not necessarily related contacts."
    )

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    st.download_button(
        label="Download selected data as a CSV table",
        data=selected_df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"extracted_{key}_{timestamp}.csv",
        mime="text/csv",
        key=f"download_{key}",
    )

    if st.button(
        "Save selected data to database",
        key=f"save_selected_{key}",
    ):
        for task in selected_types:
            try:
                added = save_records(
                    selected_df[task].dropna(),
                    task,
                )

                st.success(
                    f"Added {added} new {DISPLAY_NAMES[task]}. "
                    "Existing entries were skipped."
                )

            except sqlite3.Error as exc:
                st.error(
                    f"Could not save {DISPLAY_NAMES[task]}: {exc}"
                )


# --------------------------------------------------
# Search function
# --------------------------------------------------
@st.cache_data(ttl=600, show_spinner=False)
def fetch_query(query, num_results):
    """Fetch search HTML with a timeout and HTTP error checking."""
    response = requests.get(
        "https://www.google.com/search",
        params={
            "q": query,
            "num": num_results,
        },
        headers={
            "User-Agent": "Mozilla/5.0",
        },
        timeout=20,
    )

    response.raise_for_status()
    return response.text


# --------------------------------------------------
# Main application
# --------------------------------------------------
def main():
    # Display the title and subtitle in one banner.
    stc.html(
        """
        <div style="
            font-family:Arial, sans-serif;
            background-color:#ffffff;
            padding:18px 12px;
            border-radius:10px;
            border:3px solid #464e5f;
            text-align:center;">
            <h1 style="
                font-size:42px;
                font-weight:bold;
                color:#2457a7;
                margin:0 0 10px 0;">
                Contact Extractor
            </h1>
            <p style="
                font-size:18px;
                color:#464e5f;
                margin:0;">
                Extract emails, phone numbers, and URLs.
            </p>
        </div>
        """,
        height=150,
    )

    try:
        initialise_database()
    except sqlite3.Error as exc:
        st.error(f"Could not initialise the database: {exc}")
        st.stop()

    menu = [
        "Home",
        "Single Extractor",
        "Bulk Extractor",
        "Data Storage",
        "About",
    ]

    choice = st.sidebar.selectbox("Menu", menu)

    # --------------------------------------------------
    # Home: search and extract
    # --------------------------------------------------
    if choice == "Home":
        st.subheader("Search and Extract")

        # Countries: 193 UN member states and 2 UN observer states.
        countries_list = [
            "Afghanistan",
            "Albania",
            "Algeria",
            "Andorra",
            "Angola",
            "Antigua and Barbuda",
            "Argentina",
            "Armenia",
            "Australia",
            "Austria",
            "Azerbaijan",
            "Bahamas",
            "Bahrain",
            "Bangladesh",
            "Barbados",
            "Belarus",
            "Belgium",
            "Belize",
            "Benin",
            "Bhutan",
            "Bolivia",
            "Bosnia and Herzegovina",
            "Botswana",
            "Brazil",
            "Brunei",
            "Bulgaria",
            "Burkina Faso",
            "Burundi",
            "Cabo Verde",
            "Cambodia",
            "Cameroon",
            "Canada",
            "Central African Republic",
            "Chad",
            "Chile",
            "China",
            "Colombia",
            "Comoros",
            "Costa Rica",
            "Côte d'Ivoire",
            "Croatia",
            "Cuba",
            "Cyprus",
            "Czechia",
            "Democratic Republic of the Congo",
            "Denmark",
            "Djibouti",
            "Dominica",
            "Dominican Republic",
            "Ecuador",
            "Egypt",
            "El Salvador",
            "Equatorial Guinea",
            "Eritrea",
            "Estonia",
            "Eswatini",
            "Ethiopia",
            "Fiji",
            "Finland",
            "France",
            "Gabon",
            "Gambia",
            "Georgia",
            "Germany",
            "Ghana",
            "Greece",
            "Grenada",
            "Guatemala",
            "Guinea",
            "Guinea-Bissau",
            "Guyana",
            "Haiti",
            "Holy See (Vatican City)",
            "Honduras",
            "Hungary",
            "Iceland",
            "India",
            "Indonesia",
            "Iran",
            "Iraq",
            "Ireland",
            "Israel",
            "Italy",
            "Jamaica",
            "Japan",
            "Jordan",
            "Kazakhstan",
            "Kenya",
            "Kiribati",
            "Kuwait",
            "Kyrgyzstan",
            "Laos",
            "Latvia",
            "Lebanon",
            "Lesotho",
            "Liberia",
            "Libya",
            "Liechtenstein",
            "Lithuania",
            "Luxembourg",
            "Madagascar",
            "Malawi",
            "Malaysia",
            "Maldives",
            "Mali",
            "Malta",
            "Marshall Islands",
            "Mauritania",
            "Mauritius",
            "Mexico",
            "Micronesia",
            "Moldova",
            "Monaco",
            "Mongolia",
            "Montenegro",
            "Morocco",
            "Mozambique",
            "Myanmar",
            "Namibia",
            "Nauru",
            "Nepal",
            "Netherlands",
            "New Zealand",
            "Nicaragua",
            "Niger",
            "Nigeria",
            "North Korea",
            "North Macedonia",
            "Norway",
            "Oman",
            "Pakistan",
            "Palau",
            "Panama",
            "Papua New Guinea",
            "Paraguay",
            "Peru",
            "Philippines",
            "Poland",
            "Portugal",
            "Qatar",
            "Republic of the Congo",
            "Romania",
            "Russia",
            "Rwanda",
            "Saint Kitts and Nevis",
            "Saint Lucia",
            "Saint Vincent and the Grenadines",
            "Samoa",
            "San Marino",
            "Sao Tome and Principe",
            "Saudi Arabia",
            "Senegal",
            "Serbia",
            "Seychelles",
            "Sierra Leone",
            "Singapore",
            "Slovakia",
            "Slovenia",
            "Solomon Islands",
            "Somalia",
            "South Africa",
            "South Korea",
            "South Sudan",
            "Spain",
            "Sri Lanka",
            "State of Palestine",
            "Sudan",
            "Suriname",
            "Sweden",
            "Switzerland",
            "Syria",
            "Tajikistan",
            "Tanzania",
            "Thailand",
            "Timor-Leste",
            "Togo",
            "Tonga",
            "Trinidad and Tobago",
            "Tunisia",
            "Türkiye",
            "Turkmenistan",
            "Tuvalu",
            "Uganda",
            "Ukraine",
            "United Arab Emirates",
            "United Kingdom",
            "United States",
            "Uruguay",
            "Uzbekistan",
            "Vanuatu",
            "Venezuela",
            "Vietnam",
            "Yemen",
            "Zambia",
            "Zimbabwe",
        ]

        country = st.sidebar.selectbox(
            "Country",
            countries_list,
            index=countries_list.index("Sierra Leone"),
        )

        selected_tasks = st.sidebar.multiselect(
            "Select one, two, or all three data types",
            TASKS,
            default=TASKS,
            key="search_tasks",
        )

        # Only apply the email-domain filter when extracting emails.
        email_type = ""

        if "Emails" in selected_tasks:
            email_type = st.sidebar.selectbox(
                "Email domain",
                [
                    "Any domain",
                    "gmail.com",
                    "yahoo.com",
                    "hotmail.com",
                    "outlook.com",
                    "aol.com",
                    "hotmail.co.uk",
                    "yahoo.co.uk",
                    "live.com",
                    "icloud.com",
                    "Other",
                ],
            )

            if email_type == "Other":
                email_type = st.sidebar.text_input(
                    "Enter email domain",
                    placeholder="example.com",
                )

        num_results = st.sidebar.number_input(
            "Requested number of results",
            min_value=10,
            max_value=100,
            value=10,
            step=10,
        )

        search_text = st.text_input(
            "Enter a search term",
            placeholder="For example: university contact",
        )

        query = (
            f"{search_text.strip()} "
            f"{country.strip()}"
        ).strip()

        if (
            "Emails" in selected_tasks
            and email_type
            and email_type != "Any domain"
        ):
            query += f' "@{email_type.strip()}"'

        st.info(f"Generated query: {query}")

        st.caption(
            "Google may return a consent page or block automated requests. "
            "The requested result count is not guaranteed. "
            "Extracted items come from returned HTML and are not verified."
        )

        if st.button("Search and Extract"):
            st.session_state.pop("search_results", None)
            st.session_state.pop("result_types_search", None)

            if not search_text.strip():
                st.warning("Enter a search term.")

            elif not selected_tasks:
                st.warning("Select at least one data type.")

            elif "Emails" in selected_tasks and not email_type.strip():
                st.warning("Enter an email domain.")

            else:
                try:
                    with st.spinner("Searching and extracting..."):
                        text = fetch_query(query, int(num_results))

                        result_df = extract_results(
                            text,
                            selected_tasks,
                        )

                    st.session_state["search_results"] = result_df

                except requests.Timeout:
                    st.error("The request timed out. Try again.")

                except requests.RequestException as exc:
                    st.error(f"The search request failed: {exc}")

        # Keep results visible when downloading or saving.
        if "search_results" in st.session_state:
            show_results(
                st.session_state["search_results"],
                key="search",
            )

    # --------------------------------------------------
    # Single extractor
    # --------------------------------------------------
    elif choice == "Single Extractor":
        st.subheader("Extract One Type of Information")

        text = st.text_area(
            "Paste text here",
            height=220,
            key="single_text",
        )

        selected_task = st.sidebar.selectbox(
            "Data type",
            TASKS,
            key="single_task",
        )

        if st.button("Extract", key="extract_single"):
            st.session_state.pop("single_results", None)
            st.session_state.pop("result_types_single", None)

            if not text.strip():
                st.warning("Paste some text first.")

            else:
                st.session_state["single_results"] = extract_results(
                    text,
                    [selected_task],
                )

        if "single_results" in st.session_state:
            show_results(
                st.session_state["single_results"],
                key="single",
            )

    # --------------------------------------------------
    # Bulk extractor
    # --------------------------------------------------
    elif choice == "Bulk Extractor":
        st.subheader("Extract Selected Types of Information")

        text = st.text_area(
            "Paste text here",
            height=260,
            key="bulk_text",
        )

        selected_tasks = st.sidebar.multiselect(
            "Select one, two, or all three data types",
            TASKS,
            default=TASKS,
            key="bulk_tasks",
        )

        if st.button("Extract Selected Data", key="extract_bulk"):
            st.session_state.pop("bulk_results", None)
            st.session_state.pop("result_types_bulk", None)

            if not text.strip():
                st.warning("Paste some text first.")

            elif not selected_tasks:
                st.warning("Select at least one data type.")

            else:
                st.session_state["bulk_results"] = extract_results(
                    text,
                    selected_tasks,
                )

        if "bulk_results" in st.session_state:
            show_results(
                st.session_state["bulk_results"],
                key="bulk",
            )

    # --------------------------------------------------
    # Data storage
    # --------------------------------------------------
    elif choice == "Data Storage":
        st.subheader("Saved Extracted Data")

        selected_types = st.multiselect(
            "Select saved data to display and download",
            options=TASKS,
            default=TASKS,
            key="saved_data_types",
        )

        if not selected_types:
            st.info("Select at least one data type.")
            return

        saved_columns = {}

        try:
            for task in selected_types:
                saved_df = load_records(task)
                display_column = DATABASE_FIELDS[task][2]

                saved_columns[task] = (
                    saved_df[display_column]
                    .reset_index(drop=True)
                )

            # Align lists of different lengths into one table.
            combined_df = pd.DataFrame(saved_columns)

            if combined_df.empty:
                st.info(
                    "No saved data was found for your selection. "
                    "Extract results and save them first."
                )

            else:
                for task in selected_types:
                    count = combined_df[task].notna().sum()
                    st.write(
                        f"**Saved {DISPLAY_NAMES[task]}:** {count}"
                    )

                with st.expander("Saved Data Table", expanded=True):
                    st.dataframe(combined_df)

                st.caption(
                    "Each column is an independent list. "
                    "Items on the same row are not necessarily "
                    "related contacts."
                )

                timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

                st.download_button(
                    label="Download selected saved data as a CSV table",
                    data=combined_df.to_csv(
                        index=False
                    ).encode("utf-8-sig"),
                    file_name=f"saved_contacts_{timestamp}.csv",
                    mime="text/csv",
                    key="download_saved_table",
                )

        except (sqlite3.Error, pd.errors.DatabaseError) as exc:
            st.error(f"Could not read saved data: {exc}")

    # --------------------------------------------------
    # About
    # --------------------------------------------------
    else:
        st.subheader("About Contact Extractor")

        st.write(
            "Extract emails, phone numbers, and URLs from pasted text "
            "or web-search HTML. Select one, two, or all three types, "
            "save results to a local database, and download CSV tables."
        )

        st.write("Review saved data in the Data Storage menu.")

        st.info("JBC@2026")


if __name__ == "__main__":
    main()
    