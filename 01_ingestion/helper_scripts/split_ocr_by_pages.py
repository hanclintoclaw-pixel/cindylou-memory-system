#!/usr/bin/env python3
"""Split an OCR result.txt file into page-range chunks for parallel processing."""
import sys
import re
import os

def split_ocr(input_file, output_dir, chunks):
    """
    chunks: list of (start_page, end_page, filename_hint)
    Reads input_file, splits by ===== PAGE N ===== markers,
    writes chunks to output_dir/chunk_NNN.txt
    """
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split on page markers
    parts = re.split(r'(===== PAGE \d+ =====)', content)

    # Reconstruct page dict
    pages = {}
    current_page = 0
    for i, part in enumerate(parts):
        m = re.match(r'===== PAGE (\d+) =====', part)
        if m:
            current_page = int(m.group(1))
            pages[current_page] = part
        elif current_page > 0:
            pages[current_page] = pages.get(current_page, '') + part

    os.makedirs(output_dir, exist_ok=True)

    written = []
    for (start_page, end_page, hint) in chunks:
        chunk_text = ''
        for p in range(start_page, end_page + 1):
            if p in pages:
                chunk_text += pages[p]

        out_name = f"chunk_{start_page:03d}-{end_page:03d}_{hint}.txt"
        out_path = os.path.join(output_dir, out_name)
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(chunk_text)
        written.append((out_path, len(chunk_text)))
        print(f"Written: {out_path} ({len(chunk_text)} chars)")

    return written

if __name__ == '__main__':
    # Core Rulebook chunks based on TOC analysis
    # PDF page offset: book pages start at ~page 8 in PDF
    # The TOC shows chapters starting at these BOOK pages:
    # Intro p8, History p22, GameConcepts p40, Metahumanity p47,
    # CharCreation p52, Skills p64, Combat ~p100, Vehicles ~p118,
    # Magic p151, Matrix p203, Running p220, Beyond p242,
    # Spirits p260, StreetGear p270, Seattle p313
    # PDF pages ~= book pages + 4 (4 pages of front matter before page 8 content)

    input_file = sys.argv[1] if len(sys.argv) > 1 else 'result.txt'
    output_dir = sys.argv[2] if len(sys.argv) > 2 else 'chunks'

    # Core rulebook chunk plan (PDF page ranges)
    chunks = [
        (1,   30,  'intro_and_history'),
        (31,  65,  'game_concepts_char_creation'),
        (66,  110, 'skills_and_combat'),
        (111, 155, 'vehicles_and_magic_start'),
        (156, 210, 'magic_and_matrix'),
        (211, 260, 'running_the_shadows'),
        (261, 346, 'gear_seattle_appendices'),
    ]

    split_ocr(input_file, output_dir, chunks)
