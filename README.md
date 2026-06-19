# Mahogany DoppelFinder

**Find duplicate content beyond filenames and metadata.**

Mahogany DoppelFinder is a content-based duplicate detection tool designed to uncover duplicate content hidden inside your digital archive.

Unlike traditional duplicate finders that rely solely on filenames, folder structures, timestamps, or metadata, Mahogany analyzes the actual content of supported files to determine whether they represent the same data.

The goal is not to find similar files, but to identify files that contain the same content, even when metadata, timestamps, or other non-essential information differ.

## How It Works

Mahogany compares files within the same format family and focuses on the content they contain rather than their metadata.

For supported file types, the application extracts the actual content and generates content fingerprints using SHA256 hashes.

Examples:

* Images can be compared using their decoded pixel data.
* Audio files can be compared using their decoded PCM data.
* Video files can be compared using decoded frame data.

This approach allows Mahogany to detect duplicate content even when files have been renamed, moved, or have different metadata.

## Planned Features

### Images

* Exact duplicate detection
* Pixel-based content analysis
* Metadata-independent comparison
* Support for common image formats
* Batch scanning of large collections

### Videos

* Exact duplicate detection
* Frame-based content analysis
* Metadata-independent comparison

### Audio

* Exact duplicate detection
* PCM-based content analysis
* Metadata-independent comparison

### Archive Management

* Scan entire media libraries
* Group detected duplicates
* Review results before deletion
* Export reports

## Design Goals

* Content first
* Metadata independent
* Deterministic results
* Safe by default
* Cross-platform
* Open source

Mahogany does not attempt to find visually or acoustically similar files.

Its purpose is to identify files that contain the same underlying content.

No file is ever deleted automatically.

Users always remain in control of what happens to their data.

## Current Status

Mahogany DoppelFinder is currently in early development.

Features and implementation details may change as the project evolves.

## License

GNU General Public License v3.0 (GPLv3)
