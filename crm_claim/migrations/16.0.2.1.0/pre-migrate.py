from odoo.upgrade import util


def migrate(cr, version):
    # crm_claim to helpdesk_ticket
    util.create_column(cr, "helpdesk_stage", "_stage_id", "int4")

    cr.execute(
        """
               INSERT INTO helpdesk_stage
                (_stage_id, name, sequence, legend_blocked, legend_normal, legend_done)
                SELECT id, name, sequence, '{ "de_DE": "Blockiert", "en_EN": "Blocked" }', '{ "de_DE": "In Bearbeitung", "en_EN": "In Progress" }', '{ "de_DE": "Erledigt", "en_EN": "Done" }'
               FROM crm_claim_stage
               """
    )

    util.create_column(cr, "helpdesk_ticket_type", "_categ_id", "int4")

    cr.execute(
        """
               INSERT INTO helpdesk_ticket_type
                (_categ_id, name)
               SELECT id, name
               FROM crm_claim_category
        """
    )

    util.create_column(cr, "helpdesk_ticket", "_claim_id", "int4")
    util.create_column(cr, "helpdesk_ticket", "_categ_id", "int4")
    util.create_column(cr, "helpdesk_ticket", "_stage_id", "int4")

    cr.execute(
        """
               INSERT INTO helpdesk_ticket
               (_claim_id, _categ_id, _stage_id, name, active, sale_order_id, create_date, write_date, close_date, user_id, company_id, kanban_state)
               SELECT
               id, categ_id, stage_id, name, active, CAST(split_part(model_ref_id, ',', 2) AS INTEGER) as sale_order_id, create_date, write_date, date_closed, user_id, company_id, 'normal'
               FROM crm_claim WHERE model_ref_id like 'sale.order,%' and exists(select 1 from sale_order where id = cast(split_part(model_ref_id, ',', 2) as integer))
        """
    )

    util.merge_model(cr, "crm.claim.stage", "helpdesk.stage")
    util.merge_model(cr, "crm.claim.category", "helpdesk.ticket.type")

    cr.execute(
        """
               UPDATE helpdesk_ticket SET
                ticket_type_id = htt.id
               FROM helpdesk_ticket_type htt
               WHERE htt._categ_id = helpdesk_ticket._categ_id
               """
    )

    cr.execute(
        """
               UPDATE helpdesk_ticket SET
                stage_id = hs.id
               FROM helpdesk_stage hs
               WHERE hs._stage_id = helpdesk_ticket._stage_id
               """
    )

    util.merge_model(cr, "crm.claim", "helpdesk.ticket")
    util.remove_column(cr, "helpdesk_stage", "_stage_id")
    util.remove_column(cr, "helpdesk_ticket_type", "_categ_id")
    util.remove_column(cr, "helpdesk_ticket", "_stageg_id")
    util.remove_column(cr, "helpdesk_ticket", "_categ_id")
    util.remove_column(cr, "helpdesk_ticket", "_claim_id")
