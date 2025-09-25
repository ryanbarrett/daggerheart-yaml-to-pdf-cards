# Daggerheart YAML to PDF Cards

This repository contains `yaml-to-pdf.py`, a script that converts YAML card definitions into a printable PDF sheet.

## Card Format Requirements

Each YAML document in the input file must define a single card. The following
fields are required for every card:

- `card_id`
- `title`
- `description`
- `print_layout`
- `scenario`
- `outcome`

Other fields are optional. Any additional keys that appear in the document will
be preserved when parsing, allowing you to include campaign-specific metadata
alongside the required sections.

## Docker Image

A `Dockerfile` is provided to run the script in a containerized environment.

### Build the Image

```bash
docker build -t yaml-to-pdf .
```

### Run the Container

Mount a directory containing your YAML file and specify input and output paths inside the container:

```bash
docker run --rm -v $(pwd)/data:/data yaml-to-pdf /data/example.yaml -o /data/output.pdf
```

Replace `/data/example.yaml` with your input file and `/data/output.pdf` with the desired output path. The generated PDF will appear in your local directory because it is mounted into the container at `/data`.
