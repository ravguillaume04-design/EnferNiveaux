package fr.ravguillaume.niveaux.listeners;

import fr.ravguillaume.niveaux.NiveauxPlugin;
import fr.ravguillaume.niveaux.data.PlayerData;
import fr.ravguillaume.niveaux.util.ColorUtil;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.player.AsyncPlayerChatEvent;

/**
 * Formate les messages du chat selon le niveau du joueur.
 *
 * Format final : [Niveau X] Pseudo : message
 *
 * Note : AsyncPlayerChatEvent est déprécié sur Paper 1.19+ (remplacé par
 * io.papermc.paper.event.player.AsyncChatEvent), mais reste compatible
 * avec Spigot 1.20.x. Pour une migration Paper native, remplacer cet
 * événement et utiliser un ChatRenderer.
 */
@SuppressWarnings("deprecation")
public class ChatListener implements Listener {

    private final NiveauxPlugin plugin;

    public ChatListener(NiveauxPlugin plugin) {
        this.plugin = plugin;
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onChat(AsyncPlayerChatEvent event) {
        PlayerData data = plugin.getPlayerCache().get(event.getPlayer().getUniqueId());
        int level = (data != null) ? data.getLevel() : 0;

        // %1$s = display name Bukkit (non utilisé ici)  %2$s = message
        event.setFormat(ColorUtil.colorize(
            "&#606060[&#FFB300Niveau " + level + "&#606060] &#FFFFFF" + event.getPlayer().getName() + " &#606060: &#CCCCCC%2$s"
        ));
    }
}
