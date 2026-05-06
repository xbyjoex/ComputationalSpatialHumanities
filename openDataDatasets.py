import requests
import pandas as pd

BASE_URL = "https://opendata.leipzig.de/api/3/action/package_search"

def fetch_datasets(rows=1000):
    params = {
        "rows": rows,
        "start": 0
    }

    response = requests.get(BASE_URL, params=params)
    response.raise_for_status()

    data = response.json()

    if not data["success"]:
        raise Exception("API request failed")

    return data["result"]["results"]


def extract_info(datasets):
    result = []

    for ds in datasets:
        name = ds.get("title")
        description = ds.get("notes", "")
        created = ds.get("metadata_created")

        formats = set()
        for res in ds.get("resources", []):
            fmt = res.get("format")
            if fmt:
                formats.add(fmt.upper())

        result.append({
            "name": name,
            "created": created,
            "description": description,
            "formats": ", ".join(sorted(formats))
        })

    return result


def main():
    datasets = fetch_datasets()
    extracted = extract_info(datasets)

    df = pd.DataFrame(extracted)
    df["created"] = pd.to_datetime(df["created"], unit="s")

    # speichern
    df.to_csv("leipzig_datasets.csv", index=False)

    print(df.head())
    print(f"\nGesamt: {len(df)} Datensätze")


if __name__ == "__main__":
    main()