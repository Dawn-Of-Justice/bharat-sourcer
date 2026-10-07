<!-- Trimmed copy of https://learn.adafruit.com/magtag-weather.md?view=all fetched once on 2026-10-06
(robots.txt has no Disallow rules). Later guide pages were removed. Test fixture only:
NOT verified parts data. -->
# MagTag Daily Weather Forecast Display

## Overview

![](https://cdn-learn.adafruit.com/assets/assets/000/132/889/medium800/wireless_banner.jpg?1728319483)

Is the weather outside delightful? Or is it frightful? And what about in the coming days? In this guide we'll show you how to use an [Adafruit MagTag](https://www.adafruit.com/magtag) to create a weather display for today and future conditions.

Using the MagTag's WiFi capability, we connect to a weather API service and get weather information. We then parse that and display it up in a nice summary.

Deep sleep is also used to only run the update once a day around midnight, so we can run for many weeks on one charge.

## Weather API Services

The original code for this guide used the free [weather API service](https://openweathermap.org/api) provided by [OpenWeatherMap](https://openweathermap.org). There have been several updates to the code to keep up with API changes. However, OpenWeather now requires credit card information to obtain an API key - even if only using the free API access. **As a result, this guide no longer uses the OpenWeatherMap API**. The old code is still provided for reference.

The current version of this guide is based on the [weather API](https://open-meteo.com/en/docs) provided by [Open-Meteo](https://open-meteo.com/). This is a truly free weather API which currently does not even require an API key. It is also open source, with the code available in a&nbsp;[GitHub repo](https://github.com/open-meteo/open-meteo). This isn't a 100% drop in replacement in terms of weather forecast information provided. As a result, there are some minor differences relative to the original version.

## Parts

Here are the parts you'll need for this project. You can get them individually:

Featured
### Adafruit MagTag - 2.9" Grayscale E-Ink WiFi Display

[Adafruit MagTag - 2.9" Grayscale E-Ink WiFi Display](https://www.adafruit.com/product/4800)
The Adafruit MagTag combines the ESP32-S2 wireless module and a 2.9" grayscale E-Ink display to make a low-power IoT display that can show data on its screen even when power is removed! The ESP32-S2 is great because it builds on the years of code and support for the ESP32 and also adds...

Out of Stock
[Buy Now](https://www.adafruit.com/product/4800)
[Related Guides to the Product](https://learn.adafruit.com/products/4800/guides)
![Angled shot of rectangle-shaped electronic ink display breakout with the text: "MAGTAG 2025 Edition with SSD1680 Chipset"](https://cdn-shop.adafruit.com/640x480/4800-10.jpg)

Featured
### Lithium Ion Polymer Battery with Short Cable - 3.7V 420mAh

[Lithium Ion Polymer Battery with Short Cable - 3.7V 420mAh](https://www.adafruit.com/product/4236)
Lithium-ion polymer (also known as 'lipo' or 'lipoly') batteries are thin, light, and powerful. The output ranges from 4.2V when completely charged to 3.7V. This battery has a capacity of 420mAh for a total of about 1.55 Wh. If you need a larger (or smaller!) battery, <a...></a...>

In Stock
[Buy Now](https://www.adafruit.com/product/4236)
[Related Guides to the Product](https://learn.adafruit.com/products/4236/guides)
![Lithium Ion Polymer Battery 3.7v 420mAh with JST 2-PH connector and short cable](https://cdn-shop.adafruit.com/640x480/4236-04.jpg)

Featured
### Mini Magnet Feet for RGB LED Matrices (Pack of 4)

[Mini Magnet Feet for RGB LED Matrices (Pack of 4)](https://www.adafruit.com/product/4631)
Got a glorious&nbsp;RGB Matrix project you want to mount and display in your workspace or home? If you have one of the matrix panels listed below, you'll need a pack of these **Mini-Magnet Feet.** &nbsp;We got these specifically&nbsp;for our RGB LED Matrices, which no longer...

In Stock
[Buy Now](https://www.adafruit.com/product/4631)
[Related Guides to the Product](https://learn.adafruit.com/products/4631/guides)
![Angled shot of four magnet feet.](https://cdn-shop.adafruit.com/640x480/4631-00.jpg)

 **OR** these items are also available together as a kit:

Featured
### Adafruit MagTag Starter Kit - ADABOX017 Essentials

[Adafruit MagTag Starter Kit - ADABOX017 Essentials](https://www.adafruit.com/product/4819)
The **Adafruit MagTag** combines the new ESP32-S2 wireless module and a 2.9" grayscale E-Ink display to make a low-power IoT display that can show data on its screen even when power is removed! The ESP32-S2 is great because it builds on the years of code and support for the...

In Stock
[Buy Now](https://www.adafruit.com/product/4819)
[Related Guides to the Product](https://learn.adafruit.com/products/4819/guides)
![MagTag dev board with enclosure pieces, four magnet feet, and lipoly battery](https://cdn-shop.adafruit.com/640x480/4819-02.jpg)


<!-- [trimmed: CircuitPython setup pages] -->

# MagTag Daily Weather Forecast Display

## Project Code Install

Here is the project code and other assets. Once installed, see the next guide section for how to configure the code for your location and other settings.

## Weather Icons

The icons used in this project were inspired by this other EPD based weather project - [eInk / ePaper Weather Station](https://learn.adafruit.com/epaper-weather-station). They are the excellent set of [Meteocons](https://www.alessioatzeni.com/meteocons/) , which the [author](https://www.alessioatzeni.com/meteocons/#about) has made freely available. For this project, we converted them to gray scale, scaled them as needed, and converted to bitmap.

## Installing Project Code

To use with CircuitPython, you need to first install a few libraries, into the lib folder on your **CIRCUITPY** drive. Then you need to update **code.py** with the code listing below.

Thankfully, we can do this in one go. In the example below, click the **Download Project Bundle** button below to download the necessary libraries and the **code.py** file in a zip file. Extract the contents of the zip file, open the directory **MagTag\_Weather/** and then click on the directory that matches the version of CircuitPython you're using and copy the contents of that directory to your **CIRCUITPY** drive.

https://github.com/adafruit/Adafruit_Learning_System_Guides/blob/main/MagTag/MagTag_Weather/openmeteo/code.py

# MagTag Daily Weather Forecast Display

