#include <M5GFX.h>

static M5GFX display;

// One refresh paints one still frame. IT8951 auto-display runs on the outer endWrite.
static void draw_still(M5GFX &lcd)
{
  const int32_t panel_w = lcd.width();
  const int32_t panel_h = lcd.height();
  const bool landscape = panel_w >= panel_h;
  const int32_t span = landscape ? panel_w : panel_h;
  const int32_t cross = landscape ? panel_h : panel_w;
  int32_t side = (cross * 4) / 5;
  if (side * 2 > span) side = span / 2;
  const int32_t gap = (span - side * 2) / 3;
  const int32_t along0 = gap;
  const int32_t along1 = gap * 2 + side;
  const int32_t across = (cross - side) / 2;
  const int32_t x0 = landscape ? along0 : across;
  const int32_t y0 = landscape ? across : along0;
  const int32_t x1 = landscape ? along1 : across;
  const int32_t y1 = landscape ? across : along1;

  lcd.startWrite();
  lcd.fillScreen(0x808080u);
  lcd.fillRect(x0, y0, side, side, 0x000000u);
  lcd.fillRect(x1, y1, side, side, 0xFFFFFFu);
  lcd.endWrite();
}

void setup()
{
  display.init();
  display.setRotation(1);
  display.setBrightness(128);
  display.setColorDepth(24);
  draw_still(display);
}

void loop(void)
{
  lgfx::delay(1000);
}

#if !defined(ARDUINO)
extern "C" {
  void loopTask(void*)
  {
    setup();
    for(;;) {
      loop();
    }
  }
  void app_main()
  {
    xTaskCreatePinnedToCore( loopTask, "loopTask", 8192, NULL, 1, NULL, 1 );
  }
}
#endif
