package fr.ravguillaume.niveaux.listeners;

import fr.ravguillaume.niveaux.NiveauxPlugin;
import fr.ravguillaume.niveaux.data.PlayerData;
import fr.ravguillaume.niveaux.util.ColorUtil;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.entity.PlayerDeathEvent;

/**
 * Réinitialise le niveau et le temps d'un joueur à sa mort.
 */
public class PlayerDeathListener implements Listener {

    private final NiveauxPlugin plugin;

    public PlayerDeathListener(NiveauxPlugin plugin) {
        this.plugin = plugin;
    }

    @EventHandler(priority = EventPriority.NORMAL)
    public void onPlayerDeath(PlayerDeathEvent event) {
        PlayerData data = plugin.getPlayerCache().get(event.getEntity().getUniqueId());
        if (data == null) return;

        int levelBefore = data.getLevel();
        data.reset();

        if (levelBefore > 0) {
            event.getEntity().sendMessage(ColorUtil.colorize(
                "&#FF5555&lVous avez perdu votre niveau ! " +
                "&#606060(Niveau &#FFB300" + levelBefore + " &#606060→ &#FFB3000&#606060)"
            ));
        }
    }
}
