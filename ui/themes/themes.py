from textual.theme import Theme

# AMBER Terminal Theme - Orange/Amber ED HUD Style
amber_theme = Theme(
    name="amber",
    dark=True,
    primary="#FF8800",  # Orange/Amber - main color
    secondary="#FFAA00",  # Lighter orange
    accent="#00FF00",  # Green for actions
    warning="#FFFF00",  # Yellow for warnings
    error="#FF4444",  # Red for errors
    surface="#1a1a1a",  # Dark background
    panel="#0d0d0d",  # Darker panel background
    boost="#FFFF00",  # Yellow boost#
    variables={"font-primary-color": "#AD6F26", "font-muted-color": "#6F4A24"},
)
