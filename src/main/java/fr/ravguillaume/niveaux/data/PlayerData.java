package fr.ravguillaume.niveaux.data;

import java.util.UUID;

/**
 * Représente les données de progression d'un joueur.
 * Le niveau est toujours recalculé à partir des minutes : niveau = minutes / 60.
 */
public class PlayerData {

    private final UUID uuid;
    private String name;
    private int level;
    private int minutes;

    public PlayerData(UUID uuid, String name, int level, int minutes) {
        this.uuid = uuid;
        this.name = name;
        this.level = level;
        this.minutes = minutes;
    }

    // -------------------------------------------------------------------------
    // Méthodes de modification
    // -------------------------------------------------------------------------

    /**
     * Incrémente le compteur de minutes d'une unité et recalcule le niveau.
     *
     * @return true si le niveau a augmenté (level-up), false sinon.
     */
    public boolean addMinute() {
        this.minutes++;
        int newLevel = this.minutes / 60;
        if (newLevel > this.level) {
            this.level = newLevel;
            return true;
        }
        return false;
    }

    /**
     * Réinitialise le joueur (mort) : niveau = 0, minutes = 0.
     */
    public void reset() {
        this.level = 0;
        this.minutes = 0;
    }

    /**
     * Ajoute des niveaux. Recalcule les minutes en conséquence.
     * Le résultat est toujours >= 0.
     */
    public void addLevel(int amount) {
        this.level = Math.max(0, this.level + amount);
        this.minutes = this.level * 60;
    }

    /**
     * Retire des niveaux. Le résultat est toujours >= 0.
     * Recalcule les minutes en conséquence.
     */
    public void removeLevel(int amount) {
        this.level = Math.max(0, this.level - amount);
        this.minutes = this.level * 60;
    }

    /**
     * Définit un niveau précis et recalcule les minutes (temps = niveau * 60).
     * La valeur est toujours >= 0.
     */
    public void setLevel(int level) {
        this.level = Math.max(0, level);
        this.minutes = this.level * 60;
    }

    // -------------------------------------------------------------------------
    // Getters / Setters
    // -------------------------------------------------------------------------

    public UUID getUuid() {
        return uuid;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public int getLevel() {
        return level;
    }

    public int getMinutes() {
        return minutes;
    }
}
