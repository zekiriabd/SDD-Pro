package simfront.repository

import org.springframework.data.jpa.repository.JpaRepository
import org.springframework.stereotype.Repository
import simfront.entity.MotifInactivite

@Repository
interface MotifInactiviteRepository : JpaRepository<MotifInactivite, Long>
