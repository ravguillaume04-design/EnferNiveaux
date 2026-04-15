package fr.ravguillaume.niveaux.listeners;

import fr.ravguillaume.niveaux.NiveauxPlugin;
import fr.ravguillaume.niveaux.data.PlayerData;
import org.bukkit.Bukkit;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerJoinEvent;
import org.bukkit.event.player.PlayerQuitEvent;

import java.util.UUID;

/**
 * Gère le chargement et la sauvegarde des données de joueur
 * lors de la connexion / déconnexion.
 */
public class PlayerConnectionListener implements Listener {

    private final NiveauxPlugin plugin;

    public PlayerConnectionListener(NiveauxPlugin plugin) {
        this.plugin = plugin;
    }

    /**
     * Connexion : chargement asynchrone depuis MySQL puis injection dans le cache.
     */
    @EventHandler(priority = EventPriority.NORMAL)
    public void onPlayerJoin(PlayerJoinEvent event) {
        final UUID uuid = event.getPlayer().getUniqueId();
        final String name = event.getPlayer().getName();

        Bukkit.getScheduler().runTaskAsynchronously(plugin, () -> {
            PlayerData data = plugin.getDatabaseManager().loadPlayer(uuid, name);
            // Mise à jour du pseudo si le joueur a changé de nom
            data.setName(name);
            plugin.getPlayerCache().put(uuid, data);
        });
    }

    /**
     * Déconnexion : retrait du cache et sauvegarde asynchrone dans MySQL.
     */
    @EventHandler(priority = EventPriority.NORMAL)
    public void onPlayerQuit(PlayerQuitEvent event) {
        final UUID uuid = event.getPlayer().getUniqueId();
        final PlayerData data = plugin.getPlayerCache().remove(uuid);

        if (data != null) {
            Bukkit.getScheduler().runTaskAsynchronously(plugin, () ->
                plugin.getDatabaseManager().savePlayer(data)
            );
        }
    }
}
