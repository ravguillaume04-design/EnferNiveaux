package fr.ravguillaume.niveaux.database;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import fr.ravguillaume.niveaux.NiveauxPlugin;
import fr.ravguillaume.niveaux.data.PlayerData;

import java.sql.*;
import java.util.Collection;
import java.util.UUID;
import java.util.logging.Level;

/**
 * Gère toutes les interactions avec la base de données MySQL via HikariCP.
 *
 * Toutes les méthodes publiques sont bloquantes et doivent être appelées
 * depuis un thread asynchrone (sauf saveAllPlayers() à l'arrêt du serveur).
 */
public class DatabaseManager {

    private static final String TABLE = "niveaux_joueurs";

    private final NiveauxPlugin plugin;
    private HikariDataSource dataSource;

    public DatabaseManager(NiveauxPlugin plugin) {
        this.plugin = plugin;
    }

    // -------------------------------------------------------------------------
    // Initialisation
    // -------------------------------------------------------------------------

    /**
     * Crée le pool de connexions et la table si elle n'existe pas encore.
     *
     * @return true si la connexion a réussi, false en cas d'erreur.
     */
    public boolean init() {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(String.format(
                "jdbc:mysql://%s:%d/%s?useSSL=false&autoReconnect=true&characterEncoding=utf8&allowPublicKeyRetrieval=true",
                plugin.getConfigManager().getDatabaseHost(),
                plugin.getConfigManager().getDatabasePort(),
                plugin.getConfigManager().getDatabaseName()
        ));
        config.setUsername(plugin.getConfigManager().getDatabaseUser());
        config.setPassword(plugin.getConfigManager().getDatabasePassword());

        // Pool sizing
        config.setMaximumPoolSize(10);
        config.setMinimumIdle(2);
        config.setConnectionTimeout(30_000);
        config.setIdleTimeout(600_000);
        config.setMaxLifetime(1_800_000);

        // Prepared-statement cache
        config.addDataSourceProperty("cachePrepStmts", "true");
        config.addDataSourceProperty("prepStmtCacheSize", "250");
        config.addDataSourceProperty("prepStmtCacheSqlLimit", "2048");
        config.addDataSourceProperty("useServerPrepStmts", "true");

        config.setPoolName("NiveauxPool");

        try {
            dataSource = new HikariDataSource(config);
            createTableIfAbsent();
            return true;
        } catch (Exception e) {
            plugin.getLogger().log(Level.SEVERE,
                    "Impossible de se connecter à MySQL ! Vérifiez config.yml.", e);
            return false;
        }
    }

    private void createTableIfAbsent() throws SQLException {
        try (Connection conn = dataSource.getConnection();
             Statement stmt = conn.createStatement()) {
            stmt.executeUpdate(
                "CREATE TABLE IF NOT EXISTS " + TABLE + " (" +
                "  uuid         VARCHAR(36)  NOT NULL," +
                "  pseudo       VARCHAR(16)  NOT NULL," +
                "  niveau       INT UNSIGNED NOT NULL DEFAULT 0," +
                "  temps_minutes INT UNSIGNED NOT NULL DEFAULT 0," +
                "  PRIMARY KEY (uuid)" +
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;"
            );
        }
    }

    // -------------------------------------------------------------------------
    // CRUD
    // -------------------------------------------------------------------------

    /**
     * Charge les données d'un joueur depuis la base.
     * Si le joueur n'existe pas encore, retourne un objet vierge (niveau 0).
     */
    public PlayerData loadPlayer(UUID uuid, String name) {
        final String sql = "SELECT pseudo, niveau, temps_minutes FROM " + TABLE + " WHERE uuid = ?";
        try (Connection conn = dataSource.getConnection();
             PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setString(1, uuid.toString());
            try (ResultSet rs = ps.executeQuery()) {
                if (rs.next()) {
                    return new PlayerData(
                            uuid,
                            rs.getString("pseudo"),
                            rs.getInt("niveau"),
                            rs.getInt("temps_minutes")
                    );
                }
            }
        } catch (SQLException e) {
            plugin.getLogger().log(Level.SEVERE,
                    "Erreur lors du chargement du joueur " + name + " (" + uuid + ")", e);
        }
        return new PlayerData(uuid, name, 0, 0);
    }

    /**
     * Recherche un joueur par pseudo (insensible à la casse).
     * Retourne null si introuvable.
     */
    public PlayerData loadPlayerByName(String name) {
        final String sql =
                "SELECT uuid, pseudo, niveau, temps_minutes FROM " + TABLE + " WHERE LOWER(pseudo) = LOWER(?)";
        try (Connection conn = dataSource.getConnection();
             PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setString(1, name);
            try (ResultSet rs = ps.executeQuery()) {
                if (rs.next()) {
                    return new PlayerData(
                            UUID.fromString(rs.getString("uuid")),
                            rs.getString("pseudo"),
                            rs.getInt("niveau"),
                            rs.getInt("temps_minutes")
                    );
                }
            }
        } catch (SQLException e) {
            plugin.getLogger().log(Level.SEVERE,
                    "Erreur lors de la recherche du joueur par pseudo : " + name, e);
        }
        return null;
    }

    /**
     * Insère ou met à jour les données d'un joueur (UPSERT).
     */
    public void savePlayer(PlayerData data) {
        final String sql =
                "INSERT INTO " + TABLE + " (uuid, pseudo, niveau, temps_minutes) VALUES (?, ?, ?, ?) " +
                "ON DUPLICATE KEY UPDATE pseudo = VALUES(pseudo), niveau = VALUES(niveau), temps_minutes = VALUES(temps_minutes)";
        try (Connection conn = dataSource.getConnection();
             PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setString(1, data.getUuid().toString());
            ps.setString(2, data.getName());
            ps.setInt(3, data.getLevel());
            ps.setInt(4, data.getMinutes());
            ps.executeUpdate();
        } catch (SQLException e) {
            plugin.getLogger().log(Level.SEVERE,
                    "Erreur lors de la sauvegarde du joueur " + data.getName(), e);
        }
    }

    /**
     * Sauvegarde un ensemble de joueurs en batch (auto-save ou arrêt du serveur).
     */
    public void saveAllPlayers(Collection<PlayerData> players) {
        if (players.isEmpty()) return;

        final String sql =
                "INSERT INTO " + TABLE + " (uuid, pseudo, niveau, temps_minutes) VALUES (?, ?, ?, ?) " +
                "ON DUPLICATE KEY UPDATE pseudo = VALUES(pseudo), niveau = VALUES(niveau), temps_minutes = VALUES(temps_minutes)";
        try (Connection conn = dataSource.getConnection();
             PreparedStatement ps = conn.prepareStatement(sql)) {
            conn.setAutoCommit(false);
            for (PlayerData data : players) {
                ps.setString(1, data.getUuid().toString());
                ps.setString(2, data.getName());
                ps.setInt(3, data.getLevel());
                ps.setInt(4, data.getMinutes());
                ps.addBatch();
            }
            ps.executeBatch();
            conn.commit();
        } catch (SQLException e) {
            plugin.getLogger().log(Level.SEVERE,
                    "Erreur lors de la sauvegarde globale des joueurs", e);
        }
    }

    // -------------------------------------------------------------------------
    // Arrêt
    // -------------------------------------------------------------------------

    public void close() {
        if (dataSource != null && !dataSource.isClosed()) {
            dataSource.close();
        }
    }
}
