import fitz

def main():
    # Try different y coordinates: 740, 750, 760, 770 with a clean doc reload each time
    for y_val in [740, 750, 760, 770]:
        doc = fitz.open('/app/textbooks/9_grade/7fb9904d29_algebra_9_klass_ju_n_makarychev_2023_g_.pdf')
        page = doc[157]
        
        # Draw red mask at y_val
        rect = fitz.Rect(200, y_val, 585, 820)
        page.draw_rect(rect, color=(1, 0, 0), fill=(1, 0, 0), overlay=True)
        
        # Save crop
        clip = fitz.Rect(360, 590, 585, 820)
        pix = page.get_pixmap(clip=clip, dpi=150)
        pix.save(f'/app/test_clean_y_{y_val}.png')
        print(f"Saved test_clean_y_{y_val}.png")

if __name__ == "__main__":
    main()
