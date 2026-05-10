package simfront.entity

import jakarta.persistence.CascadeType
import jakarta.persistence.Column
import jakarta.persistence.Entity
import jakarta.persistence.FetchType
import jakarta.persistence.GeneratedValue
import jakarta.persistence.GenerationType
import jakarta.persistence.Id
import jakarta.persistence.JoinColumn
import jakarta.persistence.ManyToOne
import jakarta.persistence.OneToMany
import jakarta.persistence.Table
import java.time.LocalDateTime

@Entity
@Table(name = "PointDeVente")
class PointDeVente {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    var id: Long = 0

    @Column(name = "enseigne")
    var enseigne: String? = null

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "formatId")
    var format: Format? = null

    @Column(name = "codePostal")
    var codePostal: String? = null

    @Column(name = "commune")
    var commune: String? = null

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "natureLienId")
    var natureLien: NatureLien? = null

    @Column(name = "surface")
    var surface: Int? = null

    @Column(name = "catp")
    var catp: java.math.BigDecimal? = null

    @Column(name = "pays")
    var pays: String? = null

    @Column(name = "exploit")
    var exploit: String? = null

    @Column(name = "actif")
    var actif: Boolean = true

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "motifInactiviteId")
    var motifInactivite: MotifInactivite? = null

    @Column(name = "adresse")
    var adresse: String? = null

    @Column(name = "complementAdresse")
    var complementAdresse: String? = null

    @Column(name = "departement")
    var departement: String? = null

    @Column(name = "telephone")
    var telephone: String? = null

    @Column(name = "fax")
    var fax: String? = null

    @Column(name = "centraleDerattachement")
    var centraleDerattachement: String? = null

    @Column(name = "codeTdlinx")
    var codeTdlinx: String? = null

    @Column(name = "updatedAt")
    var updatedAt: LocalDateTime? = null

    @OneToMany(mappedBy = "pointDeVente", fetch = FetchType.LAZY, cascade = [CascadeType.ALL])
    var perimetresExploitation: MutableList<PerimetreExploitation> = mutableListOf()
}
