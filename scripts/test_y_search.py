import fitz

def main():
    doc = fitz.open('/app/textbooks/9_grade/7fb9904d29_algebra_9_klass_ju_n_makarychev_2023_g_.pdf')
    
    # Try different y coordinates: 710, 720, 730, 740
    for y_val in [710, 720, 730, 740]:
        page = doc[157]
        # Clear any drawings by reloading page
        page = doc[157]
        
        # Draw red mask at y_val
        rect = fitz.Rect(200, y_val, 585, 820)
        page.draw_rect(rect, color=(1, 0, 0), fill=(1, 0, 0), overlay=True)
        
        # Save crop
        clip = fitz.Rect(360, 590, 585, 820)
        pix = page.get_pixmap(clip=clip, dpi=150) # low dpi for fast test
        pix.save(f'/app/test_y_{y_val}.png')
        print(f"Saved test_y_{y_val}.png")

if __name__ == "__main__":
    main()
