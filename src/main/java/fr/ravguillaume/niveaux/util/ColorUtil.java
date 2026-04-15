package fr.ravguillaume.niveaux.util;

import net.md_5.bungee.api.ChatColor;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Utilitaire de colorisation des messages.
 *
 * Supporte :
 *  - Codes hex  : &#RRGGBB  (ex. &#FFB300)
 *  - Codes Bukkit : &a, &c, &l, etc.
 */
public final class ColorUtil {

    private static final Pattern HEX_PATTERN = Pattern.compile("&#([A-Fa-f0-9]{6})");

    private ColorUtil() {}

    /**
     * Traduit les codes &#RRGGBB et les codes &x en couleurs Minecraft.
     *
     * @param message message brut avec codes couleur
     * @return message prêt à l'affichage
     */
    public static String colorize(String message) {
        Matcher matcher = HEX_PATTERN.matcher(message);
        StringBuffer buffer = new StringBuffer();
        while (matcher.find()) {
            matcher.appendReplacement(buffer,
                    ChatColor.of("#" + matcher.group(1)).toString());
        }
        matcher.appendTail(buffer);
        return ChatColor.translateAlternateColorCodes('&', buffer.toString());
    }
}
